"""Uso:

    python -m extractor            # descarga, lee y genera las tablas
    python -m extractor --sin-red  # no descarga nada: usa solo lo que haya en .cache/
    python -m extractor --refrescar  # vuelve a pedir las listas (diputados y boletines)

Todo lo descargado se guarda en .cache/ (no se sube al repositorio).
No hace falta ninguna clave: las fuentes son públicas.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

from . import corts
from .construir import construir
from .md3 import aplicar_correccion, leer_declaracion, trocear
from .md4 import leer_renta
from .paginas import leer_pdf
from .red import descargar
from .util import norm

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CACHE = RAIZ / ".cache"
LEGISLATURA = "XI"


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


def _inicio_inserciones(paginas: list[dict], inserciones: list[dict]) -> list[tuple[int, dict]]:
    """En qué página empieza cada inserción (título) dentro del boletín."""
    res = []
    textos = [norm(" ".join(w["t"] for w in p.get("palabras", []) if not w.get("v"))) for p in paginas]
    for ins in inserciones:
        clave = norm(ins["titulo"].split("[")[0])[:70]
        donde = [i for i, t in enumerate(textos) if clave and clave in t]
        # el título también sale en el sumario del principio: vale la última aparición
        res.append((paginas[donde[-1]]["num"] if donde else 0, ins))
    return sorted(res, key=lambda x: x[0])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m extractor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-red", action="store_true", help="no descargar nada, usar solo .cache/")
    ap.add_argument("--refrescar", action="store_true", help="volver a pedir las listas")
    ap.add_argument("--hilos", type=int, default=None, help="procesos de OCR en paralelo")
    ap.add_argument("--solo", default="", help="leer solo estos boletines (números separados por comas); para pruebas")
    args = ap.parse_args(argv)

    c = CACHE / "corts"
    t0 = time.time()

    # 1. Quién ------------------------------------------------------------------
    diputados = corts.diputados(LEGISLATURA, c, refrescar=args.refrescar and not args.sin_red)
    _log(f"Diputados en activo: {len(diputados)}")

    # 2. Dónde ------------------------------------------------------------------
    inserciones = corts.boletines(LEGISLATURA, c, refrescar=args.refrescar and not args.sin_red)
    por_boletin: dict[str, list[dict]] = {}
    for ins in inserciones:
        por_boletin.setdefault(ins["id_bocv"], []).append(ins)
    _log(f"Boletines con declaraciones: {len(por_boletin)}")

    # 3. Leer -------------------------------------------------------------------
    f_corr = RAIZ / "correcciones" / "corts.json"
    correcciones = json.loads(f_corr.read_text(encoding="utf-8")) if f_corr.exists() else {}
    declaraciones = []
    solo = {int(n) for n in args.solo.split(",") if n.strip()}
    for id_bocv, inss in por_boletin.items():
        if solo and inss[0]["numero"] not in solo:
            continue
        pdf = c / f"{id_bocv}.pdf"
        if not pdf.exists() and not args.sin_red:
            descargar(inss[0]["url_pdf"], pdf)
        if not pdf.exists():
            _log(f"  falta {pdf.name}: se omite")
            continue
        paginas = leer_pdf(pdf, cache_dir=CACHE / "paginas", hilos=args.hilos)
        inicios = _inicio_inserciones(paginas, inss)
        grupos = trocear(paginas)
        for g in grupos:
            d = leer_declaracion(g)
            if d["sello"] in correcciones:
                d = aplicar_correccion(d, correcciones[d["sello"]])
            ins = [i for p, i in inicios if p <= g[0]["num"]]
            ins = ins[-1] if ins else inicios[0][1]
            d["tipo"] = ins["tipo"]
            d["boletin"] = {"id_bocv": id_bocv, "numero": ins["numero"], "fecha": ins["fecha"],
                            "url_pdf": ins["url_pdf"]}
            declaraciones.append(d)
        _log(f"  BOCV {inss[0]['numero']:>3}: {len(paginas)} págs, {len(grupos)} declaraciones")

    rentas = {}
    for dip in diputados:
        pdf = c / "rentas" / f"{dip['id']}.pdf"
        if not pdf.exists() and not args.sin_red:
            descargar(corts.url_renta(LEGISLATURA, dip["id"]), pdf)
        if not pdf.exists():
            continue
        try:
            r = leer_renta(leer_pdf(pdf))
        except Exception as e:
            _log(f"  renta ilegible ({dip['apellidos']}): {e!r}")
            continue
        r["url"] = corts.url_renta(LEGISLATURA, dip["id"])
        rentas[dip["id"]] = r
    _log(f"Declaraciones de rentas leídas: {len(rentas)}")

    # 4. Tablas -----------------------------------------------------------------
    boletines = [{k: i[k] for k in ("id_bocv", "numero", "fecha", "titulo", "tipo", "url_pdf")} for i in inserciones]
    meta = construir(diputados, declaraciones, rentas, boletines, LEGISLATURA, RAIZ)
    _log(f"Hecho en {time.time() - t0:.0f}s: {meta['n_personas']} personas, "
         f"{meta['n_con_declaracion']} con declaración de bienes, {meta['n_por_ocr']} leídas por OCR, "
         f"{meta['n_comprobadas']} con las sumas comprobadas, {meta['n_revisar']} para revisar, "
         f"{meta['n_ilegibles']} ilegibles, {meta['n_con_renta']} con rentas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
