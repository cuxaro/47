"""Convierte cada página de un PDF en *palabras* y *casillas* con su posición.

Los formularios de las declaraciones llegan de tres maneras dentro del boletín:

  1. rellenados en digital  -> el PDF trae el texto y los recuadros como vectores
  2. impresos y escaneados   -> la página es una imagen
  3. con las letras convertidas en trazos (sin texto ni imagen)

Para (1) se lee directamente el PDF. Para (2) y (3) se renderiza la página,
se detectan los recuadros del formulario con OpenCV y se pasa OCR (Tesseract)
casilla a casilla, que es mucho más fiable que un OCR de la página entera.

El resultado tiene la misma forma en los tres casos, así que el resto del
extractor no necesita saber de dónde salió cada dato. Las coordenadas van en
puntos PDF, con el origen arriba a la izquierda.
"""
from __future__ import annotations

import csv
import io
import json
import os
import pathlib
import re
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pdfplumber

VERSION = 3  # súbelo si cambia el formato de salida: invalida la caché
DPI = 300
IDIOMAS_OCR = "spa+cat"
MIN_PALABRAS_TEXTO = 60   # menos palabras que esto => la página no es "de texto"
MIN_TRAZOS = 150          # muchas curvas y poco texto => letras en trazos


# --------------------------------------------------------------------------- #
# Páginas con texto (formularios digitales)
# --------------------------------------------------------------------------- #
def _palabras_texto(page) -> list[dict]:
    ws = page.extract_words(y_tolerance=1.5, x_tolerance=1.5, keep_blank_chars=False)
    return [
        {"t": w["text"], "x0": round(w["x0"], 1), "x1": round(w["x1"], 1),
         "y0": round(w["top"], 1), "y1": round(w["bottom"], 1),
         "v": 0 if w.get("upright", True) else 1}
        for w in ws
    ]


def _sin_contenedores(cajas: list[tuple], tol: float) -> list[tuple]:
    """Quita los recuadros que contienen a otros: nos quedamos con los de dentro."""
    res = []
    for c in cajas:
        contiene = any(
            o is not c and o[0] >= c[0] - tol and o[1] >= c[1] - tol
            and o[2] <= c[2] + tol and o[3] <= c[3] + tol
            and (o[2] - o[0]) * (o[3] - o[1]) < 0.98 * (c[2] - c[0]) * (c[3] - c[1])
            for o in cajas
        )
        if not contiene:
            res.append(c)
    return res


def _casillas_texto(page, palabras: list[dict]) -> list[dict]:
    cajas = set()
    for r in page.rects:
        w, h = r["x1"] - r["x0"], r["bottom"] - r["top"]
        if 15 <= w <= 0.8 * page.width and 6 <= h <= 60:
            cajas.add((round(r["x0"], 1), round(r["top"], 1), round(r["x1"], 1), round(r["bottom"], 1)))
    cajas = _sin_contenedores(sorted(cajas), tol=0.6)
    res = []
    for (x0, y0, x1, y1) in cajas:
        dentro = [w for w in palabras if not w["v"]
                  and x0 - 1 <= (w["x0"] + w["x1"]) / 2 <= x1 + 1
                  and y0 - 1 <= (w["y0"] + w["y1"]) / 2 <= y1 + 1]
        dentro.sort(key=lambda w: (round(w["y0"] / 3), w["x0"]))
        res.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1,
                    "t": " ".join(w["t"] for w in dentro)})
    return res


# --------------------------------------------------------------------------- #
# Páginas escaneadas (imagen) -> OpenCV + Tesseract
# --------------------------------------------------------------------------- #
def _tesseract(entrada: str, psm: str) -> str | None:
    """Ejecuta Tesseract. Devuelve el TSV, o None si el programa falla."""
    env = dict(os.environ, OMP_THREAD_LIMIT="1")
    out = subprocess.run(
        ["tesseract", entrada, "-", "-l", IDIOMAS_OCR, "--psm", psm, "tsv"],
        capture_output=True, env=env,
    )
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def _ocr_lote(imagenes: list[str], tmp: str, nombre: str) -> list[str]:
    """OCR de una lista de recortes (una línea de texto cada uno).

    Se intenta todo de una vez, que es mucho más rápido. Si Tesseract se cae
    con algún recorte, se repite de uno en uno y ese recorte queda vacío.
    """
    if not imagenes:
        return []
    lst = os.path.join(tmp, nombre)
    with open(lst, "w") as f:
        f.write("\n".join(imagenes))
    tsv = _tesseract(lst, "7")
    textos = [""] * len(imagenes)
    if tsv is not None:
        partes: dict[int, list[str]] = {}
        for row, txt in _filas_tsv(tsv):
            partes.setdefault(int(row["page_num"]) - 1, []).append(txt)
        for i, ws in partes.items():
            if i < len(textos):
                textos[i] = " ".join(ws)
        return textos
    for i, img in enumerate(imagenes):
        tsv = _tesseract(img, "7")
        if tsv:
            textos[i] = " ".join(txt for _, txt in _filas_tsv(tsv))
    return textos


def _filas_tsv(tsv: str):
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        txt = (row.get("text") or "").strip()
        if txt and row.get("level") == "5":
            yield row, txt


def _limpia(t: str) -> str:
    """Quita restos de bordes que el OCR confunde con letras al final/principio."""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^[\|\[\]_—\-\.,:;'`\"]+\s*", "", t)
    t = re.sub(r"(\s+[\|\[\]_—\-I1lNÑi\.,:;'`\"]{1,2})+$", "", t)
    return t.strip(" |[]_")


def _igual(a: str, b: str) -> bool:
    n = lambda s: re.sub(r"[^0-9A-Za-zÀ-ÿ%,\.]", "", s).upper()
    return n(a) == n(b)


def _ocr_pagina(pdf_path: str, num: int) -> dict:
    """OCR de una página (num empieza en 1): palabras sueltas y casillas."""
    import cv2  # se importa aquí para que leer PDFs de texto no lo necesite

    k = 72.0 / DPI
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "p")
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-f", str(num), "-l", str(num),
             "-gray", "-png", "-singlefile", pdf_path, base],
            check=True, capture_output=True,
        )
        img = cv2.imread(base + ".png", cv2.IMREAD_GRAYSCALE)
        alto_px, ancho_px = img.shape

        # 1) Recuadros del formulario: líneas horizontales + verticales.
        bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        hor = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (70, 1)))
        ver = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 28)))
        rejilla = cv2.dilate(cv2.bitwise_or(hor, ver), cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
        contornos, jer = cv2.findContours(rejilla, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        cajas = []
        if jer is not None:
            for c, j in zip(contornos, jer[0]):
                if j[3] == -1:          # solo los huecos (interior de un recuadro)
                    continue
                x, y, w, h = cv2.boundingRect(c)
                if w < 60 or h < 28 or h > 500 or w > 0.9 * ancho_px:
                    continue
                if cv2.contourArea(c) < 0.7 * w * h:
                    continue
                cajas.append((x, y, x + w, y + h))
        cajas = _sin_contenedores(cajas, tol=2)

        # 2) OCR casilla a casilla, dos veces (tamaño normal y ampliado x2).
        #    Si las dos lecturas coinciden nos fiamos; si no, se marca "dudoso".
        con_tinta, listas = [], {1: [], 2: []}
        for i, (x0, y0, x1, y1) in enumerate(cajas):
            if y1 - y0 < 24 or x1 - x0 < 24:
                continue
            interior = bw[y0 + 6:y1 - 6, x0 + 6:x1 - 6]
            if interior.size == 0 or int((interior > 0).sum()) <= 40:
                continue
            rec = img[y0 + 3:y1 - 3, x0 + 3:x1 - 3]
            for esc in (1, 2):
                r = rec if esc == 1 else cv2.resize(rec, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
                r = cv2.copyMakeBorder(r, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
                fn = os.path.join(tmp, f"c{i:04d}_{esc}.png")
                cv2.imwrite(fn, r)
                listas[esc].append(fn)
            con_tinta.append(i)

        lecturas = {esc: _ocr_lote(listas[esc], tmp, f"lista{esc}.txt") for esc in (1, 2)}

        casillas = []
        orden = {i: n for n, i in enumerate(con_tinta)}
        for i, (x0, y0, x1, y1) in enumerate(cajas):
            c = {"x0": round(x0 * k, 1), "y0": round(y0 * k, 1),
                 "x1": round(x1 * k, 1), "y1": round(y1 * k, 1), "t": ""}
            if i in orden:
                a = _limpia(lecturas[1][orden[i]])
                b = _limpia(lecturas[2][orden[i]])
                c["t"] = b or a
                if not _igual(a, b):
                    c["dudoso"] = 1
                    c["alt"] = a
            casillas.append(c)

        # 3) OCR de la página entera sin la rejilla: sirve para localizar los
        #    títulos de cada apartado (no para leer los datos).
        limpio = img.copy()
        limpio[rejilla > 0] = 255
        fn = os.path.join(tmp, "limpio.png")
        cv2.imwrite(fn, limpio)
        palabras = []
        for row, txt in _filas_tsv(_tesseract(fn, "6") or ""):
            x, y, w, h = (int(row[c]) for c in ("left", "top", "width", "height"))
            palabras.append({"t": txt, "x0": round(x * k, 1), "x1": round((x + w) * k, 1),
                             "y0": round(y * k, 1), "y1": round((y + h) * k, 1), "v": 0})
    return {"palabras": palabras, "casillas": casillas}


# --------------------------------------------------------------------------- #
# Punto de entrada
# --------------------------------------------------------------------------- #
def leer_pdf(pdf_path: str | pathlib.Path, cache_dir: str | pathlib.Path | None = None,
             hilos: int | None = None) -> list[dict]:
    """Lee un PDF y devuelve una lista de páginas:

        {num, ancho, alto, metodo, palabras, casillas, sello}

    - metodo: "texto" u "ocr"
    - palabras: [{t, x0, x1, y0, y1, v}]   (v=1 si el texto va en vertical)
    - casillas: [{x0, y0, x1, y1, t, dudoso?}]  recuadros del formulario y su contenido
    - sello: palabras de la capa de texto aunque la página se lea por OCR. El
      sello del registro de entrada siempre es texto, y sirve para saber qué
      páginas pertenecen a la misma declaración.
    """
    pdf_path = str(pdf_path)
    cache = None
    if cache_dir:
        cache = pathlib.Path(cache_dir) / f"{pathlib.Path(pdf_path).stem}.v{VERSION}.json"
        if cache.exists() and cache.stat().st_mtime >= os.path.getmtime(pdf_path):
            return json.loads(cache.read_text(encoding="utf-8"))

    paginas, pendientes = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            texto = _palabras_texto(page)
            horizontales = [w for w in texto if not w["v"]]
            imagen_grande = any(
                (im["x1"] - im["x0"]) * (im["bottom"] - im["top"]) > 0.25 * page.width * page.height
                for im in page.images
            )
            en_trazos = len(page.curves) > MIN_TRAZOS
            ocr = len(horizontales) < MIN_PALABRAS_TEXTO and (imagen_grande or en_trazos)
            pag = {"num": i, "ancho": round(page.width, 1), "alto": round(page.height, 1),
                   "metodo": "ocr" if ocr else "texto", "sello": texto}
            if ocr:
                pendientes.append(pag)
            else:
                pag["palabras"] = texto
                pag["casillas"] = _casillas_texto(page, texto)
            paginas.append(pag)

    if pendientes:
        hilos = hilos or max(1, os.cpu_count() or 2)
        dir_pag = pathlib.Path(cache_dir) / pathlib.Path(pdf_path).stem if cache_dir else None

        def una(pag: dict) -> dict:
            # cada página se guarda nada más leerla: si el proceso se corta,
            # la siguiente ejecución continúa donde se quedó
            fp = dir_pag / f"p{pag['num']:04d}.v{VERSION}.json" if dir_pag else None
            if fp and fp.exists():
                return json.loads(fp.read_text(encoding="utf-8"))
            try:
                res = _ocr_pagina(pdf_path, pag["num"])
            except Exception as e:  # una página rota no debe tumbar el boletín
                return {"palabras": [], "casillas": [], "error": repr(e)[:200]}
            if fp:
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
            return res

        with ThreadPoolExecutor(max_workers=hilos) as ex:
            for pag, res in zip(pendientes, ex.map(una, pendientes)):
                pag.update(res)

    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(paginas, ensure_ascii=False), encoding="utf-8")
    return paginas


def lineas(palabras: list[dict], tol: float = 2.5) -> list[list[dict]]:
    """Agrupa palabras horizontales en líneas (arriba→abajo, izquierda→derecha)."""
    filas: list[list[dict]] = []
    for w in sorted((w for w in palabras if not w.get("v")),
                    key=lambda w: ((w["y0"] + w["y1"]) / 2, w["x0"])):
        cy = (w["y0"] + w["y1"]) / 2
        if filas:
            ult = filas[-1]
            cy_ult = sum((u["y0"] + u["y1"]) / 2 for u in ult) / len(ult)
            if abs(cy - cy_ult) <= tol:
                ult.append(w)
                continue
        filas.append([w])
    for f in filas:
        f.sort(key=lambda w: w["x0"])
    return filas
