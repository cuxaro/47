"""Une todo lo extraído y escribe las tablas finales en `datos/` y `docs/`.

Salidas:
    datos/personas.csv       una fila por persona, con los totales para filtrar
    datos/inmuebles.csv      una fila por inmueble declarado
    datos/otros_bienes.csv   una fila por bien no inmobiliario (cuentas, vehículos…)
    datos/pasivo.csv         una fila por deuda declarada
    datos/rentas.csv         una fila por partida de la declaración anual de rentas
    datos/declaraciones.json todo, incluido el histórico de declaraciones
    docs/datos.json          lo que carga la página web
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import pathlib

from .util import norm, parecido

AMBITO = "Les Corts Valencianes"


# --------------------------------------------------------------------------- #
# Emparejar cada declaración con su persona
# --------------------------------------------------------------------------- #
def _puntos(nom: str, ape: str, d: dict) -> float:
    s_todo = parecido(f"{nom} {ape}", f"{d['nombre']} {d['apellidos']}")
    s_ape = parecido(ape, d["apellidos"])
    primer = (norm(nom).split() or [""])[0]
    primer_d = (norm(d["nombre"]).split() or [""])[0]
    s_nom = max(parecido(nom, d["nombre"]), 1.0 if primer and primer in norm(d["nombre"]).split() else 0.0,
                1.0 if primer_d and primer_d in norm(nom).split() else 0.0)
    return max(s_todo, 0.75 * s_ape + 0.25 * s_nom)


def emparejar(decl: dict, personas: list[dict]) -> dict | None:
    p = decl["persona"]
    nom, ape = p.get("nombre") or "", p.get("apellidos") or ""
    if not (nom or ape):
        return None
    mejor, punt = None, 0.0
    for d in personas:
        s = _puntos(nom, ape, d)
        if s > punt:
            mejor, punt = d, s
    if punt >= 0.84:
        return mejor
    # Mismo apellido y nadie más lo lleva: es la misma persona aunque el nombre
    # esté escrito de otra forma («Xelo» / «María Consuelo»).
    if ape:
        mismos = [d for d in personas if parecido(ape, d["apellidos"]) >= 0.92]
        if len(mismos) == 1:
            return mismos[0]
    return None


def _bonito(s: str | None) -> str:
    s = (s or "").strip()
    if s.isupper() or s.islower():
        s = " ".join(w.capitalize() if w.lower() not in ("de", "del", "la", "las", "los", "i", "y") else w.lower()
                     for w in s.split())
    return s


# --------------------------------------------------------------------------- #
# Totales por persona
# --------------------------------------------------------------------------- #
def _suma(items, campo="valor", filtro=None) -> float:
    return round(sum(i[campo] for i in items if i.get(campo) is not None and (filtro is None or filtro(i))), 2)


_CAMPOS_BIENES = ("n_inmuebles", "n_viviendas", "n_viviendas_compartidas", "n_locales", "n_rusticos",
                  "n_otros_urbanos", "n_provincias", "valor_catastral", "cuentas", "vehiculos", "n_vehiculos",
                  "inversiones", "otros_bienes", "pasivo", "patrimonio_declarado")


def resumen(decl: dict | None, renta: dict | None) -> dict:
    """Totales de una persona. Si su declaración no se ha podido leer, quedan vacíos
    (None): así no cuenta ni como «tiene» ni como «no tiene»."""
    r: dict = {}
    if decl is None or decl.get("ilegible"):
        r = {k: None for k in _CAMPOS_BIENES}
        r.update(provincias_inmuebles=[], provincias_viviendas=[], tiene_hipoteca=None)
    else:
        inm, otros, pas = decl["inmuebles"], decl["otros_bienes"], decl["pasivo"]
        repetidos = decl.get("totales_repetidos", [])
        viv = [i for i in inm if i["tipo"] == "V"]
        r["n_inmuebles"] = len(inm)
        r["n_viviendas"] = len(viv)
        r["n_viviendas_compartidas"] = sum(1 for i in viv if i["porcentaje"] is not None and i["porcentaje"] < 100)
        r["n_locales"] = sum(1 for i in inm if i["tipo"] == "L")
        r["n_rusticos"] = sum(1 for i in inm if i["tipo"] == "R")
        r["n_otros_urbanos"] = sum(1 for i in inm if i["tipo"] == "O")
        provs = sorted({i["provincia"] for i in inm if i["provincia"]})
        r["provincias_inmuebles"] = provs
        r["n_provincias"] = len(provs)
        r["provincias_viviendas"] = sorted({i["provincia"] for i in viv if i["provincia"]})
        # Valor catastral: el total que escribe la persona; si no lo pone, la suma de las líneas
        total_cat = decl.get("total_catastral")
        r["valor_catastral"] = total_cat if total_cat is not None else _suma(inm, "valor_catastral")
        r["cuentas"] = _suma(otros, filtro=lambda i: i["categoria"] == "cuentas")
        r["vehiculos"] = _suma(otros, filtro=lambda i: i["categoria"] == "vehiculos")
        r["n_vehiculos"] = sum(1 for i in otros if i["categoria"] == "vehiculos")
        r["inversiones"] = _suma(otros, filtro=lambda i: i["categoria"] in ("inversiones", "pensiones", "seguros"))
        # El total que escribe la persona no siempre coincide con la suma de las líneas
        # (hay quien no detalla): nos quedamos con el mayor para no perder nada
        total_otros = None if "total_otros_bienes" in repetidos else decl.get("total_otros_bienes")
        r["otros_bienes"] = max(_suma(otros), total_otros or 0.0)
        total_pas = None if "total_pasivo" in repetidos else decl.get("total_pasivo")
        r["pasivo"] = max(_suma(pas), total_pas or 0.0)
        r["tiene_hipoteca"] = any(i["categoria"] == "hipoteca" for i in pas)
        r["patrimonio_declarado"] = round(r["valor_catastral"] + r["otros_bienes"] - r["pasivo"], 2)
    if renta:
        r["rentas"] = renta.get("total_rentas")
        r["salarios"] = renta.get("total_salarios")
        r["otras_rentas"] = round((renta.get("total_rentas") or 0) - (renta.get("total_salarios") or 0), 2)
        r["cuota_irpf"] = renta.get("cuota_irpf")
    else:
        r["rentas"] = r["salarios"] = r["otras_rentas"] = r["cuota_irpf"] = None
    return r


def _calidad(decl: dict | None) -> dict:
    """Cómo de fiable es lo leído, y si conviene revisarlo a mano.

    `revisar` solo se activa por problemas de LECTURA (OCR dudoso, tablas que no
    se localizan, datos que no se reconocen). Las rarezas de lo que la persona
    escribió (sumas que no dan, cuentas anotadas como deudas…) van en `motivos`
    como nota, pero no cuentan como error nuestro.
    """
    if not decl:
        return {"metodo": None, "revisar": True, "comprobado": False, "ilegible": False,
                "motivos": ["No se ha localizado su declaración de bienes en los boletines"]}
    lectura = list(decl.get("avisos", []))
    notas = list(decl.get("notas", []))
    items = [i for k in ("inmuebles", "otros_bienes", "pasivo") for i in decl[k]]
    es_ocr = decl["metodo"] == "ocr"
    if not decl.get("ilegible"):
        dudosos = sum(1 for i in items if i.get("dudoso"))
        if dudosos:
            lectura.append(f"{dudosos} dato(s) con lectura dudosa del OCR")
        for clave, nombre in (("suma_inmuebles_cuadra", "los inmuebles"), ("suma_otros_cuadra", "los otros bienes"),
                              ("suma_pasivo_cuadra", "las deudas")):
            if decl.get(clave) is False:
                texto = f"La suma de {nombre} no coincide con el total declarado"
                # en un formulario digital la lectura es exacta: el descuadre es de quien declara
                (lectura if es_ocr else notas).append(texto if es_ocr else texto + " (así consta en el original)")
        sin_tipo = sum(1 for i in decl["inmuebles"] if i.get("tipo") is None)
        if sin_tipo:
            lectura.append(f"{sin_tipo} inmueble(s) sin tipo reconocible")
        sin_prov = sum(1 for i in decl["inmuebles"] if i.get("provincia") is None)
        if sin_prov:
            lectura.append(f"{sin_prov} inmueble(s) sin provincia reconocible")
    comprobaciones = [decl.get(k) for k in ("suma_inmuebles_cuadra", "suma_otros_cuadra", "suma_pasivo_cuadra")]
    hechas = [c for c in comprobaciones if c is not None]
    return {"metodo": decl["metodo"], "revisar": bool(lectura), "ilegible": bool(decl.get("ilegible")),
            "comprobado": bool(hechas) and all(hechas), "motivos": lectura + notas}


def _vigente(decls: list[dict]) -> tuple[dict | None, str | None]:
    """Qué declaración refleja la situación actual de una persona.

    Normalmente, la última. Pero una «modificación» a veces solo trae lo que ha
    cambiado: si la última no tiene inmuebles y una anterior sí, se muestra la
    anterior y se avisa.
    """
    if not decls:
        return None, None
    ultima = decls[-1]
    if _tiene_bienes(ultima) and (ultima["inmuebles"] or ultima.get("total_catastral")
                                  or ultima["tipo"] != "modificacion"):
        return ultima, None
    for d in reversed(decls[:-1]):
        if d["inmuebles"] or d.get("total_catastral"):
            b = ultima["boletin"]["numero"]
            if _tiene_bienes(ultima):
                return d, (f"Hay una modificación posterior (BOCV {b}) que parece parcial: no repite los inmuebles. "
                           "Se muestra la declaración completa anterior")
            return d, f"La última declaración publicada (BOCV {b}) no trae bienes; se muestran los de la anterior"
    con_bienes = [d for d in decls if _tiene_bienes(d)]
    return (con_bienes or decls)[-1], None


def _tiene_bienes(d: dict) -> bool:
    return bool(d["inmuebles"] or d["otros_bienes"] or d["pasivo"]
                or d.get("total_catastral") or d.get("total_otros_bienes") or d.get("total_pasivo"))


# --------------------------------------------------------------------------- #
# Montaje
# --------------------------------------------------------------------------- #
def construir(diputados: list[dict], declaraciones: list[dict], rentas: dict[str, dict],
              boletines: list[dict], legislatura: str, raiz: pathlib.Path) -> dict:
    personas = [dict(d, en_activo=True, declaraciones=[]) for d in diputados]
    sueltas: list[dict] = []
    for decl in sorted(declaraciones, key=lambda d: (d.get("fecha_registro") or "", d["boletin"]["numero"])):
        per = emparejar(decl, personas) or emparejar(decl, sueltas)
        if per is None:
            p = decl["persona"]
            nom, ape = _bonito(p.get("nombre")), _bonito(p.get("apellidos"))
            per = {"id": "ex-" + (norm(f"{ape} {nom}").lower().replace(" ", "-") or decl["sello"]),
                   "slug": None, "nombre": nom or "(nombre ilegible)", "apellidos": ape,
                   "grupo": "", "circunscripcion": p.get("circunscripcion") or "",
                   "partido_declarado": _bonito(p.get("partido")),
                   "url_ficha": None, "en_activo": False, "declaraciones": []}
            sueltas.append(per)
        per["declaraciones"].append(decl)
    personas += sueltas

    salida = []
    for per in personas:
        decls = per.pop("declaraciones")
        vigente, aviso = _vigente(decls)
        renta = rentas.get(per["id"])
        cal = _calidad(vigente)
        if aviso:
            cal["motivos"].insert(0, aviso)
            cal["revisar"] = True
        fila = {
            "id": per["id"], "nombre": per["nombre"], "apellidos": per["apellidos"],
            "ambito": AMBITO, "cargo": "Diputado/a" if per["en_activo"] else "Exdiputado/a",
            "en_activo": per["en_activo"], "grupo": per.get("grupo", ""),
            "circunscripcion": per.get("circunscripcion", ""), "legislatura": legislatura,
            "url_ficha": per.get("url_ficha"),
            **resumen(vigente, renta),
            "calidad": cal,
            "declaracion": _publica(vigente) if vigente else None,
            "historico": [_ref(d) for d in decls],
            "renta": renta,
        }
        salida.append(fila)
    salida.sort(key=lambda p: (not p["en_activo"], norm(p["apellidos"]), norm(p["nombre"])))

    hoy = dt.date.today().isoformat()
    meta = {
        "generado": hoy, "ambito": AMBITO, "legislatura": legislatura,
        "boletines": boletines,
        "n_personas": len(salida), "n_en_activo": sum(p["en_activo"] for p in salida),
        "n_con_declaracion": sum(1 for p in salida if p["declaracion"]),
        "n_por_ocr": sum(1 for p in salida if p["calidad"]["metodo"] == "ocr"),
        "n_comprobadas": sum(1 for p in salida if p["calidad"]["comprobado"]),
        "n_ilegibles": sum(1 for p in salida if p["calidad"]["ilegible"]),
        "n_revisar": sum(1 for p in salida if p["calidad"]["revisar"]),
        "n_con_renta": sum(1 for p in salida if p["renta"]),
    }
    _escribir(salida, meta, declaraciones, raiz)
    return meta


def _ref(d: dict) -> dict:
    b = d["boletin"]
    return {"tipo": d["tipo"], "fecha_registro": d.get("fecha_registro"), "sello": d.get("sello"),
            "bocv": b["numero"], "fecha_bocv": b["fecha"], "paginas": [d["paginas"][0], d["paginas"][-1]],
            "url": f"{b['url_pdf']}#page={d['paginas'][0]}", "metodo": d["metodo"]}


def _publica(d: dict) -> dict:
    limpio = lambda items, campos: [{k: i.get(k) for k in campos} for i in items]
    if d.get("ilegible"):  # no publicamos lecturas que sabemos que no son fiables
        d = {**d, "inmuebles": [], "otros_bienes": [], "pasivo": [], "total_catastral": None,
             "total_otros_bienes": None, "total_pasivo": None}
    return {
        **_ref(d),
        "inmuebles": limpio(d["inmuebles"], ("clave", "tipo", "porcentaje", "provincia", "valor_catastral",
                                              "clave_txt", "tipo_txt", "porcentaje_txt", "provincia_txt", "valor_txt",
                                              "pagina", "dudoso", "corregido")),
        "otros_bienes": limpio(d["otros_bienes"], ("descripcion", "categoria", "valor", "valor_txt", "pagina", "dudoso")),
        "pasivo": limpio(d["pasivo"], ("descripcion", "categoria", "valor", "valor_txt", "pagina", "dudoso")),
        "total_catastral": d.get("total_catastral"), "total_otros_bienes": d.get("total_otros_bienes"),
        "total_pasivo": d.get("total_pasivo"),
    }


def _csv(ruta: pathlib.Path, filas: list[dict], campos: list[str]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for fila in filas:
            w.writerow({k: ("; ".join(map(str, v)) if isinstance(v, list) else v)
                        for k, v in fila.items() if k in campos})


def _escribir(personas: list[dict], meta: dict, declaraciones: list[dict], raiz: pathlib.Path) -> None:
    datos, docs = raiz / "datos", raiz / "docs"
    campos_p = ["id", "apellidos", "nombre", "ambito", "cargo", "en_activo", "grupo", "circunscripcion",
                "n_inmuebles", "n_viviendas", "n_viviendas_compartidas", "n_locales", "n_rusticos",
                "n_otros_urbanos", "n_provincias", "provincias_inmuebles", "provincias_viviendas",
                "valor_catastral", "cuentas", "vehiculos", "n_vehiculos", "inversiones", "otros_bienes",
                "pasivo", "tiene_hipoteca", "patrimonio_declarado", "rentas", "salarios", "otras_rentas",
                "cuota_irpf", "metodo_lectura", "revisar", "motivos_revision", "fecha_declaracion",
                "bocv", "url_declaracion", "url_ficha"]
    filas_p, inm, otros, pas, ren = [], [], [], [], []
    for p in personas:
        d = p["declaracion"]
        quien = {"id": p["id"], "apellidos": p["apellidos"], "nombre": p["nombre"], "grupo": p["grupo"]}
        filas_p.append({**p, "metodo_lectura": p["calidad"]["metodo"], "revisar": p["calidad"]["revisar"],
                        "motivos_revision": p["calidad"]["motivos"],
                        "fecha_declaracion": d and d["fecha_registro"], "bocv": d and d["bocv"],
                        "url_declaracion": d and d["url"]})
        if d:
            fuente = {"bocv": d["bocv"], "metodo_lectura": d["metodo"]}
            inm += [{**quien, **i, **fuente} for i in d["inmuebles"]]
            otros += [{**quien, **i, **fuente} for i in d["otros_bienes"]]
            pas += [{**quien, **i, **fuente} for i in d["pasivo"]]
        if p["renta"]:
            ren += [{**quien, "fecha_registro": p["renta"]["fecha_registro"], **x} for x in p["renta"]["partidas"]]
            if p["renta"].get("cuota_irpf") is not None:
                ren.append({**quien, "fecha_registro": p["renta"]["fecha_registro"], "apartado": "irpf",
                            "concepto": "Cuota IRPF del año anterior", "origen": "", "importe": p["renta"]["cuota_irpf"]})
    base = ["id", "apellidos", "nombre", "grupo"]
    _csv(datos / "personas.csv", filas_p, campos_p)
    _csv(datos / "inmuebles.csv", inm, base + ["clave", "tipo", "porcentaje", "provincia", "valor_catastral",
                                               "clave_txt", "tipo_txt", "provincia_txt", "valor_txt",
                                               "bocv", "pagina", "metodo_lectura", "dudoso"])
    _csv(datos / "otros_bienes.csv", otros, base + ["descripcion", "categoria", "valor", "valor_txt",
                                                    "bocv", "pagina", "metodo_lectura", "dudoso"])
    _csv(datos / "pasivo.csv", pas, base + ["descripcion", "categoria", "valor", "valor_txt",
                                            "bocv", "pagina", "metodo_lectura", "dudoso"])
    _csv(datos / "rentas.csv", ren, base + ["fecha_registro", "apartado", "concepto", "origen", "importe"])
    (datos / "declaraciones.json").write_text(
        json.dumps({"meta": meta, "declaraciones": declaraciones}, ensure_ascii=False, indent=1), encoding="utf-8")
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "datos.json").write_text(
        json.dumps({"meta": meta, "personas": personas}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
