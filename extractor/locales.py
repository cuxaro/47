"""Diputaciones y ayuntamientos: declaraciones publicadas como TOTALES.

A diferencia de Les Corts, los cargos locales solo publican el resumen del
Decreto 191/2010 (ver `modelo191.py`): valor de los inmuebles, valor de otros
bienes, total, deudas y actividades. No hay detalle inmueble a inmueble.

Fuentes implementadas:
  - Diputació de València: datos abiertos de su portal de altos cargos.
  - Diputación de Alicante: portal de transparencia (PDF de los anuncios).
  - Ayuntamientos de la provincia de València: anuncios del BOP de València.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.robotparser

from . import bopv, modelo191
from .red import AGENTE, descargar
from .util import norm, parecido

INICIO_MANDATO = "2023-06-17"   # constitución de las corporaciones tras las elecciones de mayo de 2023
FIN_CESES_ANTERIORES = "2024-01-01"   # hasta aquí, un «cese» es del mandato 2019-2023


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


# --------------------------------------------------------------------------- #
# Texto de un PDF (con OCR si hace falta)
# --------------------------------------------------------------------------- #
def _legible(t: str) -> bool:
    """¿El texto que trae el PDF sirve? Hay PDF sin texto (escaneados) y otros cuya
    fuente está mal codificada y dan símbolos sin sentido."""
    compacto = re.sub(r"\s+", "", t)
    if len(compacto) <= 200:
        return False
    raros = sum(compacto.count(c) for c in '!"#$&*+<=>?@_{|}~^[]\\\ufffd')
    return raros / len(compacto) < 0.05


def _ocr_simple(pdf: pathlib.Path, cache_ocr: pathlib.Path | None, max_paginas: int = 40) -> str:
    """OCR de página completa (los resúmenes de totales no necesitan leer casilla a casilla)."""
    f_cache = (cache_ocr / f"{pdf.stem}.ocr.txt") if cache_ocr else None
    if f_cache and f_cache.exists():
        return f_cache.read_text(encoding="utf-8")
    trozos = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "200", "-png", "-l", str(max_paginas), str(pdf), f"{tmp}/p"],
                       capture_output=True, timeout=600)
        for img in sorted(pathlib.Path(tmp).glob("p*.png")):
            r = subprocess.run(["tesseract", str(img), "-", "-l", "spa+cat", "--psm", "6"],
                               capture_output=True, timeout=300)
            trozos.append(r.stdout.decode("utf-8", "replace"))
    texto = "\n".join(trozos)
    if f_cache and texto.strip():
        f_cache.parent.mkdir(parents=True, exist_ok=True)
        f_cache.write_text(texto, encoding="utf-8")
    return texto


def texto_pdf(pdf: pathlib.Path, cache_ocr: pathlib.Path | None = None) -> tuple[str, str]:
    """Devuelve (texto, método). Si el PDF no trae texto que sirva, se pasa OCR."""
    try:
        t = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, timeout=120).stdout.decode(
            "utf-8", "replace")
    except Exception:
        t = ""
    if _legible(t):
        return t, "texto"
    try:
        ocr = _ocr_simple(pdf, cache_ocr)
    except Exception as e:
        _log(f"    OCR fallido en {pdf.name}: {e!r}")
        return t, "texto"
    return (ocr, "ocr") if len(ocr.strip()) > len(t.strip()) or not _legible(t) else (t, "texto")


def _tipo(titulo: str) -> str:
    n = norm(titulo)
    if re.search(r"\bCES|CESSAMENT|FINALI|RENUNCI|\bBAIXA\b|\bBAJA\b", n):
        return "final"
    if re.search(r"MODIFICACI|ANUAL|VARIACI", n):
        return "modificacion"
    return "inicial"


_RE_ELECTO = re.compile(r"ALCALD|BATLE|CONCEJAL|REGIDOR|TENIENTE|TINENT|DIPUTAD|PRESIDENT|PORTAVOZ|PORTAVEU", re.I)
_RE_DIRECTIVO = re.compile(r"DIRECTOR|DIRECCI|GERENT|SECRETAR|INTERVENTOR|TESORER|TRESORER|COORDINADOR|\bJEFE|\bCAP D", re.I)
_RE_CLASE = re.compile(r"^(?:TIPO DE CARGO\s+)?(Concejal(?:\s?a)?|Regidora?|Directiv[oa]|Directiu)\b[\s\-:,]*", re.I)


def _cargo(texto: str) -> tuple[str, str]:
    """Cargo tal como viene → (cargo limpio, clase: «electo» o «directivo»).

    Algunos anuncios traen «tipo de cargo» y «denominación» pegados
    («Concejal a Concejal 2023-2027», «Directivo Director General de…»)."""
    c = re.sub(r"^TIPO DE CARGO\s+", "", (texto or "").strip(), flags=re.I)
    m = _RE_CLASE.match(c)
    if m and c[m.end():].strip():
        resto = c[m.end():].strip()
        if m.group(1).lower().startswith("directi"):
            return resto, "directivo"
        # «Concejala» + «Concejala 2023-2027» → se queda la denominación
        return (resto if _RE_ELECTO.search(resto) else f"{m.group(1).replace(' a', 'a')}{' ' if re.match(r'(?:de|del|d)\b', resto) else ' · '}{resto}"), "electo"
    return c, ("directivo" if _RE_DIRECTIVO.search(c) and not _RE_ELECTO.search(c) else "electo")


def _ficha(d: dict, **extra) -> dict:
    nombre, apellidos = modelo191.partir_nombre(d["nombre_completo"])
    cargo, clase = _cargo(d.get("cargo", ""))
    return {**d, "cargo": cargo, "clase_cargo": clase, "nombre": nombre, "apellidos": apellidos, **extra}


# --------------------------------------------------------------------------- #
# Diputació de València (datos abiertos)
# --------------------------------------------------------------------------- #
DIVAL = "https://altoscargos.dival.es"


def dival(cache: pathlib.Path, sin_red: bool = False) -> tuple[list[dict], dict]:
    cache.mkdir(parents=True, exist_ok=True)
    f_p, f_d = cache / "personas.json", cache / "declaraciones.json"
    if not sin_red:
        descargar(f"{DIVAL}/personas.json", f_p, refrescar=True)
        descargar(f"{DIVAL}/declaraciones.json", f_d, refrescar=True)
    if not (f_p.exists() and f_d.exists()):
        return [], {}
    personas = {p["id"]: p for p in json.loads(f_p.read_text(encoding="utf-8"))}
    fichas = []
    for d in json.loads(f_d.read_text(encoding="utf-8")):
        per = personas.get(d["person_id"])
        if not per or not d.get("attachment_url") or (d.get("published_on") or "") < "2023-06-01":
            continue  # solo el mandato actual y las personas que siguen en la corporación
        pdf = cache / f"decl-{d['id']}.pdf"
        url = DIVAL + urllib.parse.quote(d["attachment_url"])
        if not pdf.exists() and not sin_red:
            descargar(url, pdf)
        if not pdf.exists():
            continue
        texto, metodo = texto_pdf(pdf, cache / "ocr")
        leidas = modelo191.leer(texto)
        if not leidas:
            _log(f"    Dip. València: no se ha podido leer la declaración de {per['name']}")
            leidas = [{"nombre_completo": per["name"], "cargo": "", "inmuebles": None, "otros_bienes": None,
                       "total_activo": None, "pasivo": None, "actividades": "", "ingresos_actividades": None,
                       "suma_cuadra": None, "ilegible": True}]
        partes = per["name"].split()
        for l in leidas[:1]:
            fichas.append({**l, "nombre": " ".join(partes[:-2]) or partes[0], "apellidos": " ".join(partes[-2:]),
                           "id_persona": f"dival-{per['id']}", "institucion": "Diputació de València",
                           "tipo_institucion": "Diputación", "provincia": "Valencia",
                           "grupo": per.get("political_group") or "", "cargo": (per.get("position") or "").strip()
                           or "Diputado/a provincial", "tipo": _tipo(d.get("title") or ""),
                           "fecha": d["published_on"], "metodo": metodo, "en_activo": True,
                           "fuente": "Portal de altos cargos de la Diputació de València", "url": url})
    fuente = {"nombre": "Diputació de València", "url": f"{DIVAL}/declaraciones",
              "nota": "Datos abiertos del portal de altos cargos"}
    return fichas, fuente


# --------------------------------------------------------------------------- #
# Diputación de Alicante (portal de transparencia)
# --------------------------------------------------------------------------- #
ALC = "https://abierta.diputacionalicante.es/informacion-institucional-y-organizativa/corporacion-provincial-2023-2027/"


def dipalicante(cache: pathlib.Path, sin_red: bool = False) -> tuple[list[dict], dict]:
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / "corporacion.html"
    if not sin_red:
        descargar(ALC, f, refrescar=True)
    if not f.exists():
        return [], {}
    html = f.read_text(encoding="utf-8", errors="replace")
    fichas = []
    enlaces = re.findall(r'<a[^>]+href="([^"]+\.pdf)"[^>]*>(.*?)</a>', html, re.S | re.I)
    vistos = set()
    for url, texto in enlaces:
        titulo = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto)).strip()
        if url in vistos or not re.search(r"declaraci[oó]n.*(bienes|diputad)", titulo, re.I) \
                or re.search(r"compatibilidad", titulo, re.I):
            continue
        vistos.add(url)
        pdf = cache / pathlib.Path(urllib.parse.urlparse(url).path).name
        if not pdf.exists() and not sin_red:
            descargar(url, pdf)
        if not pdf.exists():
            continue
        m = re.search(r"BOP n[uú]m\.?\s*(\d+) de (\d{1,2}) de (\w+) de (\d{4})", titulo)
        fecha = _fecha_es(m.group(2), m.group(3), m.group(4)) if m else None
        texto_decl, metodo = texto_pdf(pdf, cache / "ocr")
        for l in modelo191.leer(texto_decl):
            fichas.append(_ficha(l, institucion="Diputación de Alicante", tipo_institucion="Diputación",
                                 provincia="Alicante", grupo="", tipo=_tipo(titulo), fecha=fecha, metodo=metodo,
                                 fuente=f"BOP de Alicante nº {m.group(1)}" if m else "Portal de transparencia",
                                 url=url))
    fuente = {"nombre": "Diputación de Alicante", "url": ALC, "nota": "Anuncios del BOP colgados en su portal de transparencia"}
    return fichas, fuente


_MESES = {m: i for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(), start=1)}


def _fecha_es(dia: str, mes: str, anyo: str) -> str | None:
    n = _MESES.get(mes.lower())
    return f"{anyo}-{n:02d}-{int(dia):02d}" if n else None


# --------------------------------------------------------------------------- #
# Ayuntamientos de la provincia de València (BOP)
# --------------------------------------------------------------------------- #
def _entidad(nombre: str) -> tuple[str, str] | None:
    """«Ajuntament de Sueca / Secretaria» → («Ayuntamiento de Sueca», «Ayuntamiento»)."""
    base = nombre.split("/")[0].strip()
    m = re.match(r"Ajuntament\s+(?:de\s+l['’]|de\s+la\s+|de\s+les\s+|dels?\s+|d['’]|de\s+)(.+)", base, re.I)
    if m:
        resto = base[len("Ajuntament "):]
        # el artículo forma parte del nombre («l'Eliana», «la Pobla…»)
        resto = re.sub(r"^(de\s+|d['’])", "", resto, flags=re.I)
        return f"Ayuntamiento de {resto[0].upper() + resto[1:]}", "Ayuntamiento"
    if re.match(r"Ayuntamiento", base, re.I):
        return base, "Ayuntamiento"
    return None   # diputación, mancomunidades, consorcios… (la diputación entra por sus datos abiertos)


def ayuntamientos_valencia(cache: pathlib.Path, sin_red: bool = False,
                           limite: int | None = None) -> tuple[list[dict], dict]:
    if sin_red:
        f = cache / "indice.json"
        indice = list(json.loads(f.read_text(encoding="utf-8"))["anuncios"].values()) if f.exists() else []
    else:
        indice = bopv.recoger(cache, dt.date(2023, 6, 1), limite=limite)
    fichas, sin_leer = [], []
    for a in indice:
        ent = _entidad(a["entidad"])
        if not ent or bopv.RE_NO_SUMARIO.search(a["sumario"]):
            continue
        nombre = a["registro"].replace("/", "-")
        f_html = cache / f"{nombre}.html"
        if not f_html.exists():
            continue
        leidas = modelo191.leer_html(f_html.read_text(encoding="utf-8"))
        metodo = "texto"
        for anexo in a.get("anexos", []):
            pdf = cache / anexo["fichero"]
            if pdf.exists():
                t, m = texto_pdf(pdf, cache / "ocr")
                extra = modelo191.leer(t)
                if extra:
                    leidas += extra
                    metodo = m if m == "ocr" else metodo
        if not leidas:
            sin_leer.append(a)
            continue
        for l in leidas:
            if re.search(r"x{3,}|\*{3,}", l["nombre_completo"], re.I):
                continue        # apellidos tachados en el anuncio: no se sabe quién es
            fichas.append(_ficha(l, institucion=ent[0], tipo_institucion=ent[1], provincia="Valencia", grupo="",
                                 tipo=l.get("tipo_marcado") or _tipo(a["sumario"]), fecha=a["fecha"], metodo=metodo,
                                 fuente=f"BOP de València, anuncio {a['registro']}", url=bopv.PORTADA,
                                 registro=a["registro"]))
    con_datos = {f["institucion"] for f in fichas}
    fuente = {"nombre": "Ayuntamientos de la provincia de València", "url": bopv.PORTADA,
              "nota": f"{len(indice)} anuncios del BOP; {len(con_datos)} ayuntamientos con declaraciones leídas",
              "anuncios_sin_leer": [{"registro": a["registro"], "entidad": a["entidad"], "fecha": a["fecha"]}
                                    for a in sin_leer if _entidad(a["entidad"])]}
    return fichas, fuente


# --------------------------------------------------------------------------- #
# Ayuntamientos que cuelgan los anuncios en su propia web
# --------------------------------------------------------------------------- #
def _robots_permite(url: str, cache: pathlib.Path, sin_red: bool) -> bool:
    """Respeta el robots.txt de cada web: si prohíbe la dirección, no se descarga."""
    u = urllib.parse.urlsplit(url)
    f = cache / f"robots.{u.netloc}.txt"
    if not sin_red:
        descargar(f"{u.scheme}://{u.netloc}/robots.txt", f)
    if not f.exists():
        return True        # sin robots.txt no hay restricciones
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(f.read_text(encoding="utf-8", errors="replace").splitlines())
    return rp.can_fetch(AGENTE, url)


def _fecha_enlace(url: str, titulo: str) -> str | None:
    """Fecha del documento: del nombre del fichero (20250317-…), de la carpeta
    (/2025/03/) o, a falta de otra cosa, el año que diga el enlace."""
    m = re.search(r"(?<!\d)(20[12]\d)(0[1-9]|1[0-2])([0-3]\d)(?!\d)", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(20[12]\d)/(0[1-9]|1[0-2])/", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = re.search(r"\b(20[12]\d)\b", titulo)
    return f"{m.group(1)}-12-31" if m else None


def ayuntamientos_web(cache: pathlib.Path, sin_red: bool = False,
                      lista: pathlib.Path | None = None) -> tuple[list[dict], dict]:
    """Ayuntamientos de fuentes/ayuntamientos_web.json: una página con enlaces a
    los PDF de sus declaraciones. Para añadir uno basta con poner su página ahí."""
    lista = lista or pathlib.Path(__file__).resolve().parent.parent / "fuentes" / "ayuntamientos_web.json"
    cache.mkdir(parents=True, exist_ok=True)
    fichas, leidos, notas = [], [], []
    for ent in json.loads(lista.read_text(encoding="utf-8")):
        clave = re.sub(r"[^a-z0-9]+", "-", norm(ent["institucion"]).lower()).strip("-")
        carpeta = cache / clave
        if not _robots_permite(ent["pagina"], cache, sin_red):
            notas.append(f"{ent['institucion']}: su robots.txt no permite la lectura automática")
            continue
        f = carpeta / "pagina.html"
        if not sin_red:
            descargar(ent["pagina"], f, refrescar=True)
        if not f.exists():
            continue
        pagina = f.read_text(encoding="utf-8", errors="replace")
        servidor = urllib.parse.urlsplit(ent["pagina"]).netloc
        vistos, n = set(), 0
        for href, texto in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', pagina, re.S | re.I):
            url = urllib.parse.urljoin(ent["pagina"], html.unescape(href))
            titulo = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", texto))).strip()
            u = urllib.parse.urlsplit(url)
            # solo documentos del propio ayuntamiento (no enlaces a boletines de otros servidores)
            if u.netloc != servidor or not u.path.lower().endswith(".pdf") or url in vistos:
                continue
            if not re.search(r"declarac|bienes|b[eé]ns", url + " " + titulo, re.I):
                continue
            vistos.add(url)
            fecha = _fecha_enlace(url, titulo)
            if not fecha or fecha < "2023-06-01":
                continue
            pdf = carpeta / pathlib.Path(u.path).name
            if not pdf.exists() and not sin_red and _robots_permite(url, cache, sin_red):
                descargar(url, pdf)
            if not pdf.exists():
                continue
            texto_decl, metodo = texto_pdf(pdf, cache / "ocr")
            for l in modelo191.leer(texto_decl):
                n += 1
                fichas.append(_ficha(l, institucion=ent["institucion"], tipo_institucion="Ayuntamiento",
                                     provincia=ent["provincia"], grupo="",
                                     tipo=l.get("tipo_marcado") or _tipo(titulo + " " + u.path), fecha=fecha,
                                     metodo=metodo, fuente=f"Web del {ent['institucion']}: {titulo}"[:160], url=url))
        if n:
            leidos.append(ent["institucion"])
    fuente = {"nombre": "Ayuntamientos con las declaraciones en su web", "url": None,
              "nota": "; ".join([", ".join(leidos) or "ninguno leído"] + notas)}
    return fichas, fuente


# --------------------------------------------------------------------------- #
# De fichas a personas
# --------------------------------------------------------------------------- #
def personas(fichas: list[dict]) -> list[dict]:
    """Agrupa las fichas por persona y deja como vigente la más reciente."""
    grupos: dict[str, list[list[dict]]] = {}
    for f in sorted(fichas, key=lambda f: f.get("fecha") or ""):
        if f.get("id_persona"):
            lista = grupos.setdefault(f["institucion"], [])
            g = next((g for g in lista if g[0].get("id_persona") == f["id_persona"]), None)
        else:
            lista = grupos.setdefault(f["institucion"], [])
            g = next((g for g in lista if parecido(g[0]["nombre_completo"], f["nombre_completo"]) >= 0.9), None)
        if g is None:
            lista.append([f])
        else:
            g.append(f)

    res = []
    for inst, lista in grupos.items():
        for g in lista:
            ult = g[-1]
            # en activo: su última declaración no es de cese y es de este mandato
            activo = ult.get("en_activo")
            # Los ceses del mandato anterior (2019-2023) se publican durante 2023, a veces
            # después de la toma de posesión del nuevo: no cuentan como cese del actual.
            de_mandato = [f for f in g if (f.get("fecha") or "") >= INICIO_MANDATO
                          and not (f["tipo"] == "final" and (f.get("fecha") or "") < FIN_CESES_ANTERIORES)]
            if activo is None:
                activo = bool(de_mandato) and de_mandato[-1]["tipo"] != "final"
            # vigente: la última con importes (si sigue en el cargo, la última que no sea de cese)
            con_datos = [f for f in g if f.get("total_activo") is not None or f.get("inmuebles") is not None
                         or f.get("otros_bienes") is not None]
            preferidas = [f for f in con_datos if f in de_mandato and f["tipo"] != "final"] if activo else []
            vig = (preferidas or con_datos or g)[-1]
            ult = vig if activo else ult
            motivos, revisar = [], False
            if vig.get("ilegible") or not con_datos:
                motivos.append("No se han podido leer los importes: consulta el original")
                revisar = True
            elif vig.get("suma_cuadra") is False:
                motivos.append("Inmuebles + otros bienes no coincide con el total declarado")
                revisar = vig["metodo"] == "ocr"
            if vig.get("metodo") == "ocr":
                motivos.append("Leído por OCR de un documento escaneado")
            inm, otros = vig.get("inmuebles"), vig.get("otros_bienes")
            total = vig.get("total_activo")
            pasivo = vig.get("pasivo")
            sin_leer = not con_datos
            activo_total = total if total is not None else ((inm or 0) + (otros or 0) if con_datos else None)
            ident = ult.get("id_persona") or f"{norm(inst).lower().replace(' ', '-')}--{norm(ult['nombre_completo']).lower().replace(' ', '-')}"
            res.append({
                "id": ident, "nombre": ult["nombre"], "apellidos": ult["apellidos"],
                "ambito": inst, "institucion": inst, "tipo_institucion": ult["tipo_institucion"],
                "provincia": ult["provincia"], "detalle": "totales",
                "cargo": (ult.get("cargo") or "").strip() or ("Concejal/a" if ult["tipo_institucion"] == "Ayuntamiento" else "Diputado/a provincial"),
                "clase_cargo": ult.get("clase_cargo", "electo"),
                "en_activo": bool(activo), "grupo": ult.get("grupo", ""), "circunscripcion": ult["provincia"],
                "legislatura": "2023-2027", "url_ficha": None,
                # sin detalle: no se sabe cuántos inmuebles ni dónde
                "n_inmuebles": None, "n_viviendas": None, "n_viviendas_compartidas": None, "n_locales": None,
                "n_rusticos": None, "n_otros_urbanos": None, "n_provincias": None,
                "provincias_inmuebles": [], "provincias_viviendas": [],
                "valor_catastral": None if sin_leer else (inm if inm is not None else 0.0),
                "cuentas": None, "vehiculos": None, "n_vehiculos": None, "inversiones": None,
                "otros_bienes": None if sin_leer else (otros if otros is not None else 0.0),
                "pasivo": None if sin_leer else (pasivo if pasivo is not None else 0.0),
                "tiene_hipoteca": None,
                "patrimonio_declarado": None if activo_total is None else round(activo_total - (pasivo or 0), 2),
                "rentas": vig.get("ingresos_actividades"), "salarios": None, "otras_rentas": None, "cuota_irpf": None,
                "calidad": {"metodo": vig.get("metodo"), "revisar": revisar, "ilegible": bool(sin_leer),
                            "comprobado": vig.get("suma_cuadra") is True, "motivos": motivos},
                "declaracion": _publica(vig), "historico": [_publica(f, corto=True) for f in g], "renta": None,
            })
    return res


def _publica(f: dict, corto: bool = False) -> dict:
    base = {"tipo": f["tipo"], "fecha": f.get("fecha"), "fuente": f.get("fuente"), "url": f.get("url"),
            "metodo": f.get("metodo")}
    if corto:
        return base
    return {**base, "inmuebles_total": f.get("inmuebles"), "otros_total": f.get("otros_bienes"),
            "total_activo": f.get("total_activo"), "pasivo_total": f.get("pasivo"),
            "actividades": f.get("actividades", ""), "ingresos_actividades": f.get("ingresos_actividades"),
            "cargo_declarado": f.get("cargo", "")}
