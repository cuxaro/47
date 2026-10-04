"""Utilidades pequeñas: números, texto y comparación tolerante a erratas."""
from __future__ import annotations

import difflib
import re
import unicodedata


def sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s: str) -> str:
    """MAYÚSCULAS, sin acentos, solo letras/números y espacios simples."""
    s = sin_acentos(s or "").upper()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parecido(a: str, b: str) -> float:
    """0..1. Compara ignorando acentos, mayúsculas y espacios."""
    a, b = norm(a).replace(" ", ""), norm(b).replace(" ", "")
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


# Dos formas de escribir un importe:
#   A) con separador de miles ("35 807,98", "1.000.000", "83.503,34")
#   B) todo seguido             ("30057,72", "1747.05", "3600")
_NUM = re.compile(
    r"-?\s*(?:\d{1,3}(?:[ \.]\d{3})+(?:[,\.']\d{1,2})?(?!\d)"
    r"|\d+(?:[\.,']\d+)*)"
)


def a_numero(txt: str | None) -> float | None:
    """Interpreta importes escritos de cualquier manera:

        "35 807,98€" -> 35807.98      "1747.05 €" -> 1747.05
        "45.000"     -> 45000.0       "1.000.000" -> 1000000.0
        "-3787,09"   -> -3787.09      "45798'50"  -> 45798.5
    Devuelve None si no hay ningún número.
    """
    if not txt:
        return None
    t = txt.replace("€", " ").replace("EUR", " ").replace("euros", " ").strip()
    t = re.sub(r"(?<=\d)[:;](?=\d{3}\b)", ".", t)      # el OCR a veces lee «4:622,51» por «4.622,51»
    if re.fullmatch(r"[\dOo\.\, ]+", t) and re.search(r"\d", t):
        t = t.replace("O", "0").replace("o", "0")
    m = _NUM.search(t)
    if not m:
        return None
    s = m.group(0).replace(" ", "")
    neg = s.startswith("-")
    s = s.lstrip("-")
    if re.search(r"'\d{1,2}$", s):          # apóstrofo como coma decimal
        s = s[:s.rfind("'")].replace("'", "") + "," + s[s.rfind("'") + 1:]
    s = s.replace("'", "").rstrip(".,")
    if not s:
        return None
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        mil = "." if dec == "," else ","
        s = s.replace(mil, "").replace(dec, ".")
    elif "," in s:
        ent, _, frac = s.rpartition(",")
        s = ent.replace(",", "") + "." + frac if len(frac) in (1, 2) else s.replace(",", "")
    elif "." in s:
        ent, _, frac = s.rpartition(".")
        # "1747.05" son decimales; "45.000" o "1.000.000" son miles
        s = ent.replace(".", "") + "." + frac if len(frac) in (1, 2) else s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def a_porcentaje(txt: str | None) -> float | None:
    """ "50%" -> 50.0 ; "1/2" -> 50.0 ; "33,33 %" -> 33.33 ; "100" -> 100.0 """
    if not txt:
        return None
    m = re.search(r"(\d+)\s*/\s*(\d+)", txt)
    if m and int(m.group(2)):
        return round(100 * int(m.group(1)) / int(m.group(2)), 2)
    v = a_numero(txt.replace("%", " "))
    if v is None or v < 0 or v > 100:
        return None
    return v


PROVINCIAS = [
    "Álava", "Albacete", "Alicante", "Almería", "Asturias", "Ávila", "Badajoz", "Barcelona",
    "Burgos", "Cáceres", "Cádiz", "Cantabria", "Castellón", "Ciudad Real", "Córdoba", "Cuenca",
    "Girona", "Granada", "Guadalajara", "Gipuzkoa", "Huelva", "Huesca", "Illes Balears", "Jaén",
    "A Coruña", "La Rioja", "Las Palmas", "León", "Lleida", "Lugo", "Madrid", "Málaga", "Murcia",
    "Navarra", "Ourense", "Palencia", "Pontevedra", "Salamanca", "Santa Cruz de Tenerife",
    "Segovia", "Sevilla", "Soria", "Tarragona", "Teruel", "Toledo", "Valencia", "Valladolid",
    "Bizkaia", "Zamora", "Zaragoza", "Ceuta", "Melilla",
]
_ALIAS_PROV = {
    "ALACANT": "Alicante", "CASTELLO": "Castellón", "CASTELLON DE LA PLANA": "Castellón",
    "CASTELLO DE LA PLANA": "Castellón", "VALENCIA": "Valencia", "BALEARES": "Illes Balears",
    "ISLAS BALEARES": "Illes Balears", "MALLORCA": "Illes Balears", "IBIZA": "Illes Balears",
    "VIZCAYA": "Bizkaia", "BISCAIA": "Bizkaia", "GUIPUZCOA": "Gipuzkoa", "GERONA": "Girona",
    "LERIDA": "Lleida", "TEROL": "Teruel", "CONCA": "Cuenca", "LA CORUNA": "A Coruña",
    "ORENSE": "Ourense", "SARAGOSSA": "Zaragoza", "MURCIA": "Murcia", "OSCA": "Huesca",
    "ALBACETE": "Albacete", "TENERIFE": "Santa Cruz de Tenerife",
}
_PROV_NORM = {norm(p): p for p in PROVINCIAS} | _ALIAS_PROV


def a_provincia(txt: str | None) -> str | None:
    """Devuelve el nombre normalizado de la provincia, o None si no se reconoce."""
    n = norm(txt or "")
    if not n:
        return None
    if n in _PROV_NORM:
        return _PROV_NORM[n]
    for clave, prov in sorted(_PROV_NORM.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(clave)}\b", n):
            return prov
    mejor = difflib.get_close_matches(n, list(_PROV_NORM), n=1, cutoff=0.8)
    return _PROV_NORM[mejor[0]] if mejor else None
