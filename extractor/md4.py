"""Lee el formulario MD4 de Les Corts: «Declaración anual de rentas».

Es un PDF de texto, con cinco apartados:
   I   percepciones salariales          (concepto, origen, cuantía)
   II  dividendos                       (concepto, cuantía)
   III intereses                        (concepto, cuantía)
   IV  otras rentas                     (concepto, cuantía)
   V   cuota del IRPF del año anterior  (cuantía)
"""
from __future__ import annotations

import re

from .paginas import lineas
from .util import a_numero

_APARTADOS = {"I.": "salarios", "II.": "dividendos", "III.": "intereses", "IV.": "otras", "V.": "irpf"}
_RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+\d{2}:\d{2}\b")


def _limpia(t: str) -> str:
    return re.sub(r"\(cid:\d+\)", "", t).strip().rstrip("+").strip()


def leer_renta(paginas: list[dict]) -> dict:
    r = {"fecha_registro": None, "estado_civil": None, "regimen_matrimonial": None,
         "partidas": [], "cuota_irpf": None}
    todo = " ".join(w["t"] for p in paginas for w in p["palabras"])
    m = _RE_FECHA.search(todo)
    if m:
        r["fecha_registro"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    apartado, x_origen, x_cuantia, previa = None, 290.0, 430.0, ""
    for pag in paginas:
        for l in lineas([w for w in pag["palabras"] if 100 < w["y0"] < pag["alto"] - 60]):
            txt = " ".join(w["t"] for w in l)
            t0 = l[0]["t"]
            if t0 in _APARTADOS and len(l) > 3:
                apartado = _APARTADOS[t0]
                continue
            if t0 in ("Concepte", "Concepto"):
                for w in l:
                    if w["t"] == "Origen":
                        x_origen = w["x0"] - 3
                    if w["t"] in ("Quantia", "Cuantía"):
                        x_cuantia = w["x0"] - 3
                continue
            if txt.startswith("Estat civil"):
                previa = txt
                continue
            if previa.startswith("Estat civil") and not txt.startswith("Estado civil"):
                r["estado_civil"] = " ".join(w["t"] for w in l if w["x0"] < 250) or None
                r["regimen_matrimonial"] = " ".join(w["t"] for w in l if w["x0"] >= 250) or None
                previa = ""
                continue
            if apartado is None or "€" not in txt:
                continue
            importe = a_numero(" ".join(w["t"] for w in l if w["x0"] >= x_cuantia))
            if importe is None:
                continue
            if apartado == "irpf":
                r["cuota_irpf"] = importe
                continue
            if t0 in ("Quantia", "Cuantía"):
                continue
            concepto = _limpia(" ".join(w["t"] for w in l if w["x0"] < (x_origen if apartado == "salarios" else x_cuantia)))
            origen = _limpia(" ".join(w["t"] for w in l if x_origen <= w["x0"] < x_cuantia)) if apartado == "salarios" else ""
            r["partidas"].append({"apartado": apartado, "concepto": concepto, "origen": origen, "importe": importe})
    for ap in ("salarios", "dividendos", "intereses", "otras"):
        r["total_" + ap] = round(sum(p["importe"] for p in r["partidas"] if p["apartado"] == ap), 2)
    r["total_rentas"] = round(sum(p["importe"] for p in r["partidas"]), 2)
    return r
