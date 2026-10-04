"""Lee el «modelo 191»: el resumen de la declaración que ayuntamientos y
diputaciones publican en el Boletín Oficial de la Provincia.

El Decreto 191/2010 del Consell solo obliga a publicar TOTALES por persona:

    Titular del cargo
    Cargo público origen de la declaración
    I.   Activo:  1. bienes inmuebles   2. valor total de otros bienes   3. total
    II.  Pasivo (créditos, préstamos, deudas)
    III. Actividades

No hay detalle: ni cuántos inmuebles, ni dónde, ni qué cuentas. Cada
ayuntamiento lo maqueta a su manera (texto corrido, tablas, castellano o
valenciano), así que el lector busca los rótulos y coge los importes que hay
entre uno y otro.
"""
from __future__ import annotations

import html as html_mod
import re

from .util import a_numero, norm, sin_acentos

# Líneas que son «mobiliario» de la página del boletín, no contenido
_RE_MOBILIARIO = re.compile(
    r"butllet[ií] oficial|bolet[ií]n oficial|edita excma|^\s*p[aàá]g\.?\s*\d+|^\s*n[uú]m\.?\s*\d+\s*$"
    r"|verificable a|^\s*csv\s*:|^\s*\d{1,2}-\d{1,2}-\d{4}\s*\d*\s*$|^\s*\d+\s*/\s*20\d\d\s*$|^\s*\d{1,3}\s*$",
    re.I)

# Dónde empieza la ficha de cada persona (cada ayuntamiento lo rotula a su manera)
_RE_TITULAR = re.compile(
    r"TITULAR\s+DEL?\s+C[AÀ]R(?:GO|REC)(?:\s*/\s*TITULAR\s+DEL\s+CARGO)?"
    r"|NOM(?:BRE)?\s+DEL?\s+(?:LA\s+)?DECLARANTE?"
    r"|(?:^|\n)[ \t]*(?:\d+\s*[\.\-\)]?\s*)?TITULAR\s*:"
    r"|(?:^|\n)[ \t]*NOM(?:BRE)?(?:\s+[IY]\s+(?:COGNOMS|APELLIDOS))?\s*:"
    r"|(?:^|\n)[ \t]*(?:\d+\s+)?DENOMINACI[OÓ]N?\s+DEL\s+C[AÀ]R(?:GO|REC)", re.I)
_RE_CARGO = re.compile(r"C[AÀ]R(?:GO|REC)\s+(?:P[UÚ]BLIC[O]?\s+)?(?:D[E']?\s*)?ORIGEN[^\n:]*:?"
                       r"|C[AÀ]R(?:GO|REC)\s+P[UÚ]BLIC[O]?\s*:", re.I)
_RE_TIPO_MARCADO = re.compile(r"\b[xX✓✔]\s+(INICIAL|FINAL|MODIFICACI)", re.I)
_RE_ACTIVO = re.compile(r"(?:^|\n)[ \t]*(?:I\s*[\.\-\)]*\s*)?ACTI(?:VO|U)\b[ \t]*:?", re.I)
_RE_PASIVO = re.compile(r"(?:^|\n)[ \t]*(?:II\s*[\.\-\)]*\s*)?PASS?I(?:VO|U)\b[^\n:]*:?", re.I)
_RE_ACTIVIDADES = re.compile(r"(?:^|\n)[ \t]*(?:III\s*[\.\-\)]*\s*)?ACTIVI(?:DADES|TATS)\b[ \t.…]*:?", re.I)
_RE_INMUEBLES = re.compile(r"(?:1\s*[\.\-\)]*\s*)?(?:VALOR\s+(?:DE\s+)?(?:L[OE]S\s+)?)?(?:B(?:IENES|[EÉ]NS)\s+)?I[NM]M(?:UEBLES|OBLES)", re.I)
_RE_OTROS = re.compile(r"(?:2\s*[\.\-\)]*\s*)?(?:VALOR\s+TOTAL\s+(?:DE\s+(?:LOS\s+)?|D['’]\s*)?)?(?:OTROS|ALTRES)\s+B(?:IENES|[EÉ]NS)", re.I)
_RE_TOTAL = re.compile(r"(?:3\s*[\.\-\)]*\s*)TOTAL\b|(?:^|\n)[ \t\-\.]*(?:VALOR\s+)?TOTAL\b", re.I)
_RE_IMPORTE = re.compile(r"-?\d{1,3}(?:[\. ]\d{3})+(?:[,'’\.]\d{1,2})?(?!\d)|-?\d+(?:[,'’\.]\d{1,2})?(?!\d)")
_ETIQUETAS_NOMBRE = re.compile(
    r"\b(NOM(?:BRE)?\s+DEL?\s+(?:LA\s+)?DECLARANTE?|PRIMER\s+(?:COGNOM|APELLIDO)|SEGON\s+COGNOM|SEGUNDO\s+APELLIDO"
    r"|NOM(?:BRE)?\s+(?:DEL\s+)?TITULAR|COGNOMS?|APELLIDOS?|NOMBRE|NOM|IMPORTE?S?|DO[ÑN]A|DON|D[ÑN]A|SRA?|D)\b\.?\s*:?", re.I)


def html_a_texto(fragmento: str) -> str:
    """HTML de un anuncio → texto con saltos de línea donde había bloques."""
    t = re.sub(r"<(script|style).*?</\1>", " ", fragmento, flags=re.S | re.I)
    t = re.sub(r"<(br|/p|/div|/tr|/td|/th|/li|/h\d)[^>]*>", "\n", t, flags=re.I)
    t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", t))


def _limpia(texto: str) -> str:
    lineas = [l for l in texto.replace("\r", "").replace("\f", "\n").split("\n") if not _RE_MOBILIARIO.search(l)]
    return "\n".join(lineas)


def _importes(trozo: str) -> list[float]:
    """Importes en euros de un trozo de texto (sin porcentajes ni números de rótulo)."""
    # Ojo: no se pueden borrar los paréntesis enteros, porque en muchos anuncios el
    # importe queda en medio de la aclaración («(según valor catastral… 99.737,53 € …titularidad)»).
    t = trozo
    t = re.sub(r"(?m)(^|\s)[1-3]\s*[\.\)](?=\s|$)", " ", t)   # y los números de apartado («1.», «2.»)
    res = []
    for m in _RE_IMPORTE.finditer(t):
        resto = t[m.end():m.end() + 3]
        if "%" in resto:
            continue
        v = a_numero(m.group(0).replace("’", "'"))
        if v is not None:
            res.append(v)
    return res


def _suma(trozo: str) -> float | None:
    vals = _importes(trozo)
    if vals:
        return round(sum(vals), 2)
    return 0.0 if re.search(r"-{2,}|—|\bning[uú]n|\bcap\b|\bno\b|\bsin\b|\bsense\b", trozo, re.I) else None


def _nombre(trozo: str) -> str:
    t = _ETIQUETAS_NOMBRE.sub(" ", trozo.replace(":", " ").replace("/", " "))
    t = re.sub(r"[^\wÀ-ÿ'’\-\. ]+", " ", t.replace("\n", " "))
    t = re.sub(r"\s+", " ", t).strip(" .-")
    return t if 3 <= len(t) <= 80 else ""


_RE_CELDA_IMPORTE = re.compile(r"^-?\s*\d[\d\. ]*(?:[,'’]\d{1,2})?\s*(?:€|euros?)?$|^[-—–]+\s*€?$", re.I)
_NO_NOMBRE = re.compile(r"\b(TOTAL|ACTIU|ACTIVO|PASSIU|PASIVO|B[EÉ]NS|BIENES|IMMOBLES|INMUEBLES|TITULAR|REGISTR[OE]|NOMBRE|"
                        r"NOM|COGNOMS|APELLIDOS|C[AÀ]RREC|CARGO|ALTRES|OTROS|VALOR|DECLARACI\w*|ANUNCI\w*|CORPORACI\w*|"
                        r"AJUNTAMENT|AYUNTAMIENTO|CR[EÈ]DITS?|CR[EÉ]DITOS?|ACTIVI\w+|INICI|FINAL)\b", re.I)


def _es_nombre(celda: str, minimo: int = 2) -> bool:
    palabras = celda.replace(".", " ").split()
    return (minimo <= len(palabras) <= 6 and not _NO_NOMBRE.search(celda)
            and all(re.fullmatch(r"[A-Za-zÀ-ÿ'’ªº\-]+", w) for w in palabras))


def _leer_tabla(texto: str) -> list[dict]:
    """Anuncios en forma de tabla: una fila por persona con sus importes
    (inmuebles, otros bienes, total y, a veces, pasivo)."""
    celdas = []
    for l in texto.split("\n"):
        celdas += [c.strip() for c in re.split(r"\s{2,}|\t", l.strip()) if c.strip()]
    res, i = [], 0
    while i < len(celdas):
        if not _es_nombre(celdas[i]):
            i += 1
            continue
        nombre, j, cargo = celdas[i], i + 1, ""
        # entre el nombre y los importes puede ir el cargo
        while j < len(celdas) and j - i <= 2 and not _RE_CELDA_IMPORTE.match(celdas[j]):
            cargo = (cargo + " " + celdas[j]).strip()
            j += 1
        importes = []
        while j < len(celdas) and _RE_CELDA_IMPORTE.match(celdas[j]) and len(importes) < 4:
            importes.append(a_numero(celdas[j]) or 0.0)
            j += 1
        if len(importes) >= 3 and abs(importes[0] + importes[1] - importes[2]) <= 1:
            res.append({"nombre_completo": nombre, "cargo": cargo[:120] if _es_nombre(cargo) or len(cargo) < 60 else "",
                        "inmuebles": importes[0], "otros_bienes": importes[1], "total_activo": importes[2],
                        "pasivo": importes[3] if len(importes) > 3 else None, "actividades": "",
                        "ingresos_actividades": None, "suma_cuadra": True})
            i = j
        else:
            i += 1
    return res


def _leer_tabla_alineada(texto: str) -> list[dict]:
    """Tabla que conserva las columnas (PDF): la fila de cada persona tiene los
    importes en una línea y el nombre, el cargo y las actividades pueden seguir
    en las líneas de debajo, cada uno en su columna."""
    filas, actual = [], None
    for linea in texto.split("\n"):
        celdas = [(m.start(), m.group(0)) for m in re.finditer(r"\S+(?: \S+)*", linea)]
        k = next((i for i, (_, c) in enumerate(celdas) if _RE_CELDA_IMPORTE.match(c)), None)
        importes = []
        if k is not None:
            j = k
            while j < len(celdas) and _RE_CELDA_IMPORTE.match(celdas[j][1]) and len(importes) < 4:
                importes.append(a_numero(celdas[j][1]) or 0.0)
                j += 1
        if k and len(importes) >= 3 and abs(importes[0] + importes[1] - importes[2]) <= 1 and _es_nombre(celdas[0][1], 1):
            actual = {"nombre": [celdas[0][1]], "cargo": [c for _, c in celdas[1:k]], "act": [c for _, c in celdas[j:]],
                      "importes": importes, "col_cargo": celdas[1][0] if k > 1 else celdas[k][0],
                      "col_importes": celdas[k][0], "col_act": celdas[j - 1][0] + len(celdas[j - 1][1])}
            filas.append(actual)
        elif actual and celdas and not re.fullmatch(r"\d+\s*/\s*\d+", linea.strip()):
            for pos, c in celdas:
                if pos < actual["col_cargo"] - 2:
                    if _es_nombre(c, 1):
                        actual["nombre"].append(c)
                elif pos < actual["col_importes"] - 2:
                    actual["cargo"].append(c)
                elif pos >= actual["col_act"]:
                    actual["act"].append(c)
    return [{"nombre_completo": " ".join(f["nombre"]), "cargo": " ".join(f["cargo"])[:120],
             "inmuebles": f["importes"][0], "otros_bienes": f["importes"][1], "total_activo": f["importes"][2],
             "pasivo": f["importes"][3] if len(f["importes"]) > 3 else None,
             "actividades": re.sub(r"\s+", " ", " ".join(f["act"]))[:400], "ingresos_actividades": None,
             "suma_cuadra": True} for f in filas if len(" ".join(f["nombre"]).split()) >= 2]


def leer(texto: str) -> list[dict]:
    """Texto de un anuncio (o de su anexo) → una ficha por persona."""
    texto = _limpia(texto)
    return _leer_fichas(texto) or _leer_tabla_alineada(texto) or _leer_tabla(texto)


def _leer_fichas(texto: str) -> list[dict]:
    cortes = [m.start() for m in _RE_TITULAR.finditer(texto)]
    # «Titular del cargo» y «Nombre del declarante» suelen ir seguidos: son la misma persona
    inicios = [c for i, c in enumerate(cortes) if i == 0 or c - cortes[i - 1] > 60]
    res = []
    for i, ini in enumerate(inicios):
        bloque = texto[ini:inicios[i + 1] if i + 1 < len(inicios) else len(texto)]
        cabecera = _RE_TITULAR.match(bloque)
        m_cargo = _RE_CARGO.search(bloque)
        m_act = _RE_ACTIVO.search(bloque, m_cargo.end() if m_cargo else 0)
        if not m_act:
            continue
        m_pas = _RE_PASIVO.search(bloque, m_act.end())
        m_acd = _RE_ACTIVIDADES.search(bloque, (m_pas or m_act).end())
        fin_activo = (m_pas or m_acd).start() if (m_pas or m_acd) else len(bloque)
        activo = bloque[m_act.end():fin_activo]

        m_inm, m_otr = _RE_INMUEBLES.search(activo), _RE_OTROS.search(activo)
        m_tot = None
        for m in _RE_TOTAL.finditer(activo):
            if not m_otr or m.start() > m_otr.end():
                m_tot = m
                break
        fin_inm = (m_otr or m_tot).start() if (m_otr or m_tot) else len(activo)
        fin_otr = m_tot.start() if m_tot else len(activo)
        inmuebles = _suma(activo[m_inm.end():fin_inm]) if m_inm else None
        otros = _suma(activo[m_otr.end():fin_otr]) if m_otr else None
        total = _suma(activo[m_tot.end():]) if m_tot else None

        pasivo = None
        if m_pas:
            pasivo = _suma(bloque[m_pas.end():m_acd.start() if m_acd else len(bloque)])
        actividades = ""
        if m_acd:
            actividades = re.sub(r"\s+", " ", bloque[m_acd.end():]).strip(" .:…")
            # el texto de cierre del anuncio no es una actividad
            actividades = re.split(r"\b(?:Lo que se hace p[uú]blico|La qual cosa|Contra (?:el|la) presente|"
                                   r"En \w+, a \d|[A-ZÀ-Ý][\wà-ÿ' ]+, \d{1,2} d[e']\s*\w+ de 20\d\d)", actividades)[0].strip(" .,;")
        imp_act = _importes(actividades) if actividades and len(actividades) < 40 else []

        nombre = _nombre(bloque[cabecera.end():m_cargo.start() if m_cargo else m_act.start()])
        cargo = ""
        if re.search(r"DENOMINACI", cabecera.group(0), re.I):
            # formato «Denominación del cargo: X» y debajo «Nombre titular / Apellidos»
            resto = bloque[cabecera.end():m_act.start()].strip(" :\n\t")
            m_nom = re.search(r"NOM(?:BRE)?\s+(?:DEL\s+)?TITULAR", resto, re.I)
            linea, debajo = (resto[:m_nom.start()], resto[m_nom.start():]) if m_nom else resto.partition("\n")[::2]
            cargo = re.sub(r"\s+", " ", linea).strip(" .:-")
            # si el cargo ocupa dos líneas, la primera queda encima del rótulo
            antes = texto[:ini + 1].rstrip(" \t\n").split("\n") if texto[ini:ini + 1] == "\n" and "\n\n" not in \
                texto[max(0, ini - 3):ini + 1].replace(" ", "") else []
            if antes and not re.search(r"\d", antes[-1]) and len(antes[-1].strip()) < 60 \
                    and (len(antes) < 2 or not antes[-2].strip()):
                cargo = f"{antes[-1].strip()} {cargo}"
            cargo = cargo[:120]
            nombre = _nombre(debajo)
        elif m_cargo:
            cargo = re.sub(r"\b(TIPUS DE C[AÀ]RREC|TIPO DE CARGO|TIPUS DE DECLARACI[OÓ]N?|TIPO DE DECLARACI[OÓ]N?"
                           r"|DENOMINACI[OÓ]N?|INICIAL|FINAL|MODIFICACI[OÓ]N?)\b\s*:?", " ",
                           bloque[m_cargo.end():m_act.start()].replace("/", " "), flags=re.I)
            cargo = re.sub(r"(?<!\w)[xX✓✔](?!\w)", " ", cargo)
            cargo = re.sub(r"\s+", " ", cargo).strip(" .:-")[:120]
        # «Con ocasión de cese / toma de posesión» pegado al nombre: es el tipo de declaración
        ocasion = re.search(r"\s*\b(?:Con ocasi[oó]n|Amb ocasi[oó]|En ocasi[oó]n?) de(?: la| el)? (cese|cessament|toma|presa)\b.*$",
                            nombre, re.I)
        if ocasion:
            nombre = nombre[:ocasion.start()].strip()
        if not nombre:
            continue
        cuadra = None
        if total is not None and (inmuebles is not None or otros is not None):
            cuadra = abs((inmuebles or 0) + (otros or 0) - total) <= 1
        res.append({
            "nombre_completo": nombre, "cargo": cargo,
            "inmuebles": inmuebles, "otros_bienes": otros, "total_activo": total, "pasivo": pasivo,
            "actividades": actividades[:400], "ingresos_actividades": round(sum(imp_act), 2) if imp_act else None,
            "suma_cuadra": cuadra,
        })
        if ocasion:
            res[-1]["tipo_marcado"] = "final" if ocasion.group(1).lower().startswith("ces") else "inicial"
        m_tipo = _RE_TIPO_MARCADO.search(bloque[:m_act.start()])
        if m_tipo:
            res[-1]["tipo_marcado"] = {"I": "inicial", "F": "final", "M": "modificacion"}[m_tipo.group(1)[0].upper()]
    return res


def partir_nombre(nombre_completo: str) -> tuple[str, str]:
    """«GEMA ALEMÁN PÉREZ» → («Gema», «Alemán Pérez»). Aproximado: se asume
    que los dos últimos elementos son los apellidos."""
    partes = nombre_completo.split()
    particulas = {"de", "del", "la", "las", "los", "i", "y", "d'", "san", "santa"}
    bonito = lambda ps: " ".join(p.lower() if p.lower() in particulas - {"san", "santa"} else p.capitalize() if p.isupper() or p.islower() else p
                                 for p in ps)
    if len(partes) <= 2:
        return bonito(partes[:1]), bonito(partes[1:])
    corte = len(partes) - 2
    # «Ferrer San Segundo», «García de la Torre»: la partícula arrastra al apellido anterior
    while corte > 1 and (sin_acentos(partes[corte - 1]).lower() in particulas
                         or sin_acentos(partes[corte]).lower() in particulas):
        corte -= 1
    return bonito(partes[:corte]), bonito(partes[corte:])
