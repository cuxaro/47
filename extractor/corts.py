"""Fuente: Les Corts Valencianes (diputados y diputadas).

Tres cosas se sacan de su web, todas públicas:

  1. La lista de diputados de la legislatura.
  2. Los boletines (BOCV) donde se publican las declaraciones de actividades
     y bienes: la inicial, las modificaciones anuales y las finales.
  3. La «declaración anual de rentas» de cada diputado (un PDF por persona).
"""
from __future__ import annotations

import json
import pathlib
import re

from bs4 import BeautifulSoup

from .red import descargar

BASE = "https://www.cortsvalencianes.es"
API_BOCV = f"{BASE}/publicaciones-CV"


def url_boletin(id_bocv: str) -> str:
    return f"{API_BOCV}/obtenerPdfBO?f_id_bocv={id_bocv}&idioma=es_ES"


def url_renta(leg: str, id_dip: str) -> str:
    return f"{BASE}/es/external-data/pdf/{leg}/{id_dip}"


def url_ficha(leg: str, slug: str, id_dip: str) -> str:
    return f"{BASE}/es/composicion/diputados/{leg.lower()}/{slug}/{id_dip}"


def diputados(leg: str, cache: pathlib.Path, refrescar: bool = False) -> list[dict]:
    """Lista de diputados en activo: id, nombre, grupo, circunscripción."""
    f = descargar(f"{BASE}/es/composicion/diputados?legislature={leg}",
                  cache / f"diputados_{leg}.html", refrescar=refrescar)
    if not f:
        raise RuntimeError("No se ha podido descargar la lista de diputados")
    sopa = BeautifulSoup(f.read_text(encoding="utf-8"), "lxml")
    res, vistos = [], set()
    for tr in sopa.select("table tbody tr"):
        a = tr.find("a", href=re.compile(r"/composicion/diputados/[a-z]+/[^/]+/[0-9a-f]{32}"))
        if not a:
            continue
        m = re.search(r"/composicion/diputados/([a-z]+)/([^/]+)/([0-9a-f]{32})", a["href"])
        id_dip = m.group(3)
        if id_dip in vistos:
            continue
        vistos.add(id_dip)
        tds = tr.find_all("td")
        nombre = tds[1].get_text(" ", strip=True)            # "Apellidos, Nombre"
        ape, _, nom = nombre.partition(",")
        img = tds[2].find("img") if len(tds) > 2 else None
        grupo = re.sub(r"^Foto de\s+", "", (img.get("alt") or img.get("title") or "")) if img else ""
        res.append({
            "id": id_dip, "slug": m.group(2), "nombre": nom.strip(), "apellidos": ape.strip(),
            "grupo": grupo.strip(),
            "circunscripcion": tds[3].get_text(" ", strip=True) if len(tds) > 3 else "",
            "url_ficha": url_ficha(leg, m.group(2), id_dip),
        })
    return res


def boletines(leg: str, cache: pathlib.Path, refrescar: bool = False) -> list[dict]:
    """Inserciones del BOCV que publican declaraciones de actividades y bienes."""
    f = descargar(f"{API_BOCV}/obtenerListaNumerosBO", cache / f"bocv_{leg}.json", refrescar=refrescar, datos={
        "idioma": "es_ES", "member": "", "rpp": "-1", "select": "", "f_legislatura": leg,
        "f_fecha_publicacion": "", "f_fasciculo_decimal": "", "f_numero_bocv": "",
        "insf_texto": "", "insf_titulo": "bienes patrimoniales",
    })
    if not f:
        raise RuntimeError("No se ha podido consultar el buscador del BOCV")
    # El servidor responde en ISO-8859-15 y con tabuladores sueltos dentro del JSON
    crudo = f.read_bytes().decode("iso-8859-15").replace("\t", " ").replace("\r\n", " ")
    datos = json.loads(crudo, strict=False)["dades"]
    res = []
    for ins in datos.get("inserciones", []):
        titulo = re.sub(r"</?HTML>", "", ins["titulo"]).strip()
        t = titulo.lower()
        if "pregunta" in t or "actividades" not in t or "bienes" not in t:
            continue
        if re.search(r"\b[ivx]+ legislatura\b", t) and f"de la {leg.lower()} legislatura" not in t:
            continue  # declaraciones finales de la legislatura anterior
        if t.startswith("modificaci"):
            tipo = "modificacion"
        elif "declaraciones finales" in t or "declaración final" in t:
            tipo = "final"
        else:
            tipo = "inicial"
        fp = ins["fecha_publicacion"]
        res.append({
            "id_bocv": ins["id_bocv"], "numero": int(ins["numero_bocv"]),
            "fecha": f"{fp[:4]}-{fp[4:6]}-{fp[6:]}", "titulo": titulo, "tipo": tipo,
            "url_pdf": url_boletin(ins["id_bocv"]),
        })
    res.sort(key=lambda b: (b["fecha"], b["numero"], b["tipo"]))
    return res
