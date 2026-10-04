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
    r"|(?:^|\n)[ \t]*NOM(?:BRE)?(?:\s+[IY]\s+(?:COGNOMS|APELLIDOS))?(?:\s+DE(?:L|LS|\s+LOS)?\s+(?:LA\s+)?TITULARE?S?)?\s*:"
    r"|(?:^|\n)[ \t]*NOM(?:BRE)?\s+PRIMER\s+(?:COGNOM|APELLIDO)"
    r"|(?:^|\n)[ \t]*(?:\d+\s+)?DENOMINACI[OÓ]N?\s+DEL\s+C[AÀ]R(?:GO|REC)", re.I)
_RE_CARGO = re.compile(r"C[AÀ]R(?:GO|REC)\s+(?:P[UÚ]BLIC[O]?\s+)?(?:D[E']?\s*)?ORIGEN[^\n:]*:?"
                       r"|C[AÀ]R(?:GO|REC)\s+P[UÚ]BLIC[O]?\s*:", re.I)
_RE_TIPO_MARCADO = re.compile(r"\b[xX✓✔]\s+(INICIAL|FINAL|MODIFICACI)", re.I)
_RE_ACTIVO = re.compile(r"(?:^|\n)[ \t]*(?:[I1l|]\s*[\.\-\)]*\s*)?ACTI(?:VO|U)\b[ \t]*:?", re.I)
_RE_PASIVO = re.compile(r"(?:^|\n)[ \t]*(?:[I1l|]{2}\s*[\.\-\)]*\s*)?PASS?I(?:VO|U)\b[^\n:]*:?", re.I)
_RE_ACTIVIDADES = re.compile(r"(?:^|\n)[ \t]*(?:[I1l|]{3}\s*[\.\-\)]*\s*)?ACTIVI(?:DADES|TATS)\b[ \t.…]*:?", re.I)
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
    t = re.sub(r"\.?\s*[´`]\s*(?=\d{2}(?!\d))", ",", trozo)      # «401.500.´00», «2.000´00»: decimales con tilde
    t = re.sub(r"(?m)(^|\s)[1-3]\s*[\.\)](?=\s|$)", " ", t)
    t = re.sub(r"(?m)(^|\s)\d{1,2}\s*[\.\)\-]+\s*(?=[A-Za-zÀ-ÿ])", " ", t)       # «2-Valor…», «1.Préstecs»   # y los números de apartado («1.», «2.»)
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
    if re.search(r"-{2,}|—|\bning[uú]n|\bcap\b|\bno\b|\bsin\b|\bsense\b", trozo, re.I):
        return 0.0
    return 0.0 if re.search(r"(?m)\s[O0]{1,2}\s*$", trozo) else None      # el OCR lee «0» como «O»


def _nombre(trozo: str) -> str:
    t = _ETIQUETAS_NOMBRE.sub(" ", trozo.replace(":", " ").replace("/", " "))
    t = re.sub(r"[^\wÀ-ÿ'’\-\. ]+", " ", t.replace("\n", " "))
    t = re.sub(r"\s+", " ", t).strip(" .-")
    return t if 3 <= len(t) <= 80 else ""


_RE_CELDA_IMPORTE = re.compile(r"^-?\s*\d[\d\. ]*(?:[,'’]\d{1,2})?\s*(?:€|euros?)?$|^[-—–]+\s*€?$", re.I)
_NO_NOMBRE = re.compile(r"\b(TOTAL|ACTIU|ACTIVO|PASSIU|PASIVO|B[EÉ]NS|BIENES|IMMOBLES|INMUEBLES|TITULAR|REGISTR[OE]|NOMBRE|"
                        r"NOM|COGNOMS|APELLIDOS|C[AÀ]RREC|CARGO|ALTRES|OTROS|VALOR|DECLARACI\w*|ANUNCI\w*|CORPORACI\w*|"
                        r"AJUNTAMENT|AYUNTAMIENTO|CR[EÈ]DITS?|CR[EÉ]DITOS?|ACTIVI\w+|INICI[O]?|FINAL|DATA|FECHA|EUROS?|IMPORTE?S?|"
                        r"ENTI[TD]A[TD]|EMPRESA|ORGANISM[EO]|MOTIU|MOTIVO|CESE|CESSAMENT|GRUPO?|PARTIDO?|PARTIT|PASS?I[UV]O?)\b", re.I)


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


# --------------------------------------------------------------------------- #
# Tablas en HTML con cabecera (una fila por persona)
# --------------------------------------------------------------------------- #
def tablas_html(fragmento: str) -> list[list[list[str]]]:
    """Tablas del HTML como filas de celdas, deshaciendo celdas combinadas."""
    tablas = []
    # solo las tablas más interiores: el anuncio entero va dentro de otra tabla de maquetación
    for t in re.findall(r"<table\b(?:(?!<table\b).)*?</table>", fragmento, re.S | re.I):
        rejilla: list[list[str]] = []
        pendientes: dict[int, tuple[int, str]] = {}      # columna → (filas que quedan, texto)
        for tr in re.findall(r"<tr\b.*?</tr>", t, re.S | re.I):
            fila, col = [], 0
            celdas = re.findall(r"<t[dh]\b([^>]*)>(.*?)</t[dh]>", tr, re.S | re.I)
            k = 0
            while k < len(celdas) or col in pendientes:
                if col in pendientes:
                    quedan, txt = pendientes[col]
                    fila.append(txt)
                    if quedan > 1:
                        pendientes[col] = (quedan - 1, txt)
                    else:
                        del pendientes[col]
                    col += 1
                    continue
                atributos, cuerpo = celdas[k]
                k += 1
                txt = re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", cuerpo)).replace("\xa0", " ")).strip()
                ancho = int((re.search(r"colspan\s*=\s*['\"]?(\d+)", atributos, re.I) or [0, 1])[1])
                alto = int((re.search(r"rowspan\s*=\s*['\"]?(\d+)", atributos, re.I) or [0, 1])[1])
                for _ in range(max(1, ancho)):
                    fila.append(txt)
                    if alto > 1:
                        pendientes[col] = (alto - 1, txt)
                    col += 1
            if any(fila):
                rejilla.append(fila)
        if rejilla:
            tablas.append(rejilla)
    return tablas


def _tipo_columna(rotulo: str) -> str | None:
    r = norm(rotulo)
    if re.search(r"PASS?I[UV]|DEUTES|DEUDAS|PRESTE?C|PRESTAMO|CREDIT", r):
        return "pasivo"
    inm = re.search(r"I[NM]M(UEBLES|OBLES)|I[NM]MOBILIARI|CA[TD]ASTRAL", r)
    otros = re.search(r"(ALTRES|OTROS|RESTO|RESTA)\b.*B(IENES|ENS)|B(IENES|ENS) (MUEBLES|MOBLES)|\bMOBLES\b|\bMUEBLES\b"
                      r"|^\W*(\d\W*)*(OTROS|ALTRES)\b", r)
    if re.search(r"TOTAL.*ACTI(U|VO)\b|ACTI(U|VO)\b.*TOTAL|1\s*\+\s*2", rotulo, re.I) or (inm and otros):
        return "total_activo"
    if inm:
        return "inmuebles"
    if otros:
        return "otros_bienes"
    if re.search(r"^(I )?ACTI(U|VO)\b", r):
        return "total_activo"
    if re.search(r"\bTOTAL\b", r):
        return "total"        # «Total» a secas: del activo, salvo que cuelgue de «Pasivo»
    if re.search(r"INGRESS?OS|RETRIBUCI|\bRENDES\b|\bRENTAS?\b", r):
        return "ingresos"
    if re.search(r"ACTIVI(TAT|DAD)|OCUPACI|PROFESSI|PROFESI|ENTITAT|ENTIDAD", r):
        return "actividades"
    if re.search(r"COGNOMS?|APELLIDOS?", r) and not re.search(r"\bNOM\b|NOMBRE", r):
        return "apellidos"
    if re.search(r"\bNOM\b|NOMBRE|COGNOMS|APELLIDOS|TITULAR|DADES|DATOS|DECLARANT", r):
        return "nombre"
    if re.search(r"CARREC|CARGO", r):
        return "cargo"
    if re.search(r"MOTIU|MOTIVO|TIPUS|TIPO|OCASIO", r):
        return "motivo"
    return None


def _nombre_celda(celda: str) -> tuple[str, str]:
    """«PÉREZ GIL, ANA (Regidora PP)» → («ANA PÉREZ GIL», «Regidora PP»)."""
    cargo = " ".join(re.findall(r"\(([^)]*)\)", celda))
    n = re.sub(r"\([^)]*\)", " ", celda)
    n = re.sub(r"^\s*\d+\s*[\.\-\)]*\s*", "", n)
    n = re.sub(r"^(?:D\.?ª|DÑA\.?|DOÑA|DON|SRA?\.?|D\.)\s+", "", n.strip(), flags=re.I)
    if n.count(",") == 1:
        apellidos, nombre = [x.strip() for x in n.split(",")]
        n = f"{nombre} {apellidos}"
    return re.sub(r"\s+", " ", n).strip(" .-:"), cargo.strip()


def _parece_nombre(n: str) -> bool:
    palabras = n.replace(".", ". ").split()
    return (2 <= len(palabras) <= 7 and not _NO_NOMBRE.search(n)
            and all(re.fullmatch(r"[A-Za-zÀ-ÿ'’ªº\-\.]+", w) for w in palabras))


def _celda_importe(celda: str) -> float | None:
    c = celda.strip()
    if not c:
        return None
    if re.fullmatch(r"[-—–\.]+\s*€?|0+", c):
        return 0.0
    c = re.sub(r"^(\d{1,3}(?:[,\.]\d+)?\s*%\s*)+", "", c)                 # «50 % 40.366,02 €»
    c = re.sub(r"\s*(€|euros?|eur)?\.?\s*\**\s*$", "", c, flags=re.I)
    c = re.sub(r"(?<=\d)\s+(?=[,\.]\d)|(?<=\d[,\.])\s+(?=\d)", "", c)      # «0 ,00»
    return a_numero(c) if _RE_CELDA_IMPORTE.match(c) else None


def leer_tablas(tablas: list[list[list[str]]]) -> list[dict]:
    """Tablas con una fila por persona. La cabecera dice qué es cada columna."""
    res: list[dict] = []
    columnas: list[str | None] = []
    for rejilla in tablas:
        ancho = max(len(f) for f in rejilla)
        filas = [f + [""] * (ancho - len(f)) for f in rejilla]
        if len(columnas) != ancho:       # si no, puede ser la misma tabla que sigue en otra página
            columnas = [None] * ancho
        con_cabecera = False
        for fila in filas:
            # cabecera: ninguna celda es un importe y alguna dice qué columna es
            tipos = [_tipo_columna(c) if c else None for c in fila]
            n_imp = sum(_celda_importe(c) is not None for c in fila)
            con_persona = any(t is None and "," not in c and len(c.split()) >= 3 and _parece_nombre(c)
                              for t, c in zip(tipos, fila))
            if n_imp == 0 and sum(t is not None for t in tipos) >= 2 and not con_persona:
                # la primera fila de cabecera de cada tabla empieza de cero; las siguientes la completan
                if con_cabecera:
                    tipos = [columnas[i] if t is None or (t == "total" and columnas[i] == "pasivo") else t
                             for i, t in enumerate(tipos)]
                columnas = ["total_activo" if t == "total" else t for t in tipos]
                con_cabecera = True
                # «Activo» con tres columnas debajo: inmuebles, otros bienes y total, por este orden
                del_activo = [i for i, t in enumerate(columnas) if t in ("inmuebles", "otros_bienes", "total_activo")]
                if len(del_activo) == 3 and del_activo[2] - del_activo[0] == 2:
                    for i, t in zip(del_activo, ("inmuebles", "otros_bienes", "total_activo")):
                        columnas[i] = t
                if "nombre" not in columnas and "apellidos" not in columnas and columnas[0] is None:
                    columnas[0] = "nombre"      # columna de nombres sin rótulo
                continue
            if "nombre" not in columnas and "apellidos" not in columnas:
                continue
            d: dict = {}
            for tipo, celda in zip(columnas, fila):
                if tipo == "actividades":
                    d[tipo] = (d.get(tipo, "") + " · " + celda).strip(" ·") if celda.strip(" -·") else d.get(tipo, "")
                elif tipo and tipo not in d:
                    d[tipo] = celda
            nombre, cargo = _nombre_celda(d.get("nombre", ""))
            if "apellidos" in d:
                nombre = f"{nombre} {_nombre_celda(d['apellidos'])[0]}".strip()
            if not _parece_nombre(nombre):
                continue
            actividades = d.get("actividades", "")
            if not any(c in columnas for c in ("total_activo", "inmuebles", "otros_bienes")):
                # segunda tabla solo con las actividades: se añaden a la ficha de esa persona
                for f in res:
                    if f["nombre_completo"] == nombre and actividades and not f["actividades"]:
                        f["actividades"] = actividades[:400]
                continue
            val = {k: _celda_importe(d.get(k, "")) for k in ("inmuebles", "otros_bienes", "total_activo", "pasivo", "ingresos")}
            ingresos = val["ingresos"]
            if ingresos is None and _celda_importe(actividades) is not None:
                ingresos, actividades = _celda_importe(actividades), ""
            elif ingresos is None and len(actividades) < 80:
                imp = [v for v in _importes(actividades) if v >= 100]
                ingresos = round(sum(imp), 2) if imp else None
            cuadra = None
            partes = val["inmuebles"] is not None or val["otros_bienes"] is not None
            if val["total_activo"] is None and partes:
                val["total_activo"] = round((val["inmuebles"] or 0) + (val["otros_bienes"] or 0), 2)
            elif val["total_activo"] is not None and partes:
                cuadra = abs((val["inmuebles"] or 0) + (val["otros_bienes"] or 0) - val["total_activo"]) <= 1
            elif val["total_activo"] is None and val["pasivo"] is None:
                if not (actividades or ingresos is not None or d.get("cargo") or cargo):
                    continue
                val["total_activo"] = 0.0          # fila con las casillas de bienes en blanco
            ficha = {"nombre_completo": nombre, "cargo": (d.get("cargo") or cargo).strip()[:120],
                     "inmuebles": val["inmuebles"], "otros_bienes": val["otros_bienes"],
                     "total_activo": val["total_activo"], "pasivo": val["pasivo"],
                     "actividades": actividades[:400], "ingresos_actividades": ingresos, "suma_cuadra": cuadra}
            motivo = norm(d.get("motivo", ""))
            if re.search(r"\bCES|FINAL|BAIXA|BAJA|RENUNCI", motivo):
                ficha["tipo_marcado"] = "final"
            elif re.search(r"TOMA|PRESA|INICI|POSSE|POSE", motivo):
                ficha["tipo_marcado"] = "inicial"
            elif re.search(r"MODIFIC|ANUAL|VARIACI", motivo):
                ficha["tipo_marcado"] = "modificacion"
            res.append(ficha)
    return res


def leer_html(fragmento: str) -> list[dict]:
    """HTML de un anuncio → una ficha por persona (tablas con cabecera o texto)."""
    de_texto = leer(html_a_texto(fragmento))
    de_tabla = leer_tablas(tablas_html(fragmento))
    nombres = lambda fichas: {norm(f["nombre_completo"]) for f in fichas}
    return de_tabla if de_tabla and len(nombres(de_tabla)) >= len(nombres(de_texto)) * 0.8 else de_texto


def leer(texto: str) -> list[dict]:
    """Texto de un anuncio (o de su anexo) → una ficha por persona."""
    texto = _limpia(texto)
    return _leer_fichas(texto) or _leer_tabla_alineada(texto) or _leer_tabla(texto) or _leer_por_activo(texto)


def _leer_fichas(texto: str) -> list[dict]:
    cortes = [m.start() for m in _RE_TITULAR.finditer(texto)]
    # «Titular del cargo» y «Nombre del declarante» suelen ir seguidos: son la misma persona
    inicios = [c for i, c in enumerate(cortes) if i == 0 or c - cortes[i - 1] > 60]
    # si el rótulo va numerado («2.-Titular del cargo: …»), el número es de esta ficha, no de la anterior
    for k, c in enumerate(inicios):
        linea = texto.rfind("\n", 0, c + 1) if texto[c:c + 1] != "\n" else c
        if re.fullmatch(r"\s*\d+\s*[\.\-\)ºª]*\s*", texto[linea + 1:c] if linea < c else ""):
            inicios[k] = linea + 1
    res = []
    for i, ini in enumerate(inicios):
        bloque = texto[ini:inicios[i + 1] if i + 1 < len(inicios) else len(texto)]
        cabecera = _RE_TITULAR.search(bloque)
        m_cargo = _RE_CARGO.search(bloque)
        m_act = _RE_ACTIVO.search(bloque, m_cargo.end() if m_cargo else 0)
        if not m_act:
            # sin rótulo «Activo»: los importes empiezan en «Inmuebles: …»
            m_act = re.compile(r"(?=(?:^|\n)[ \t]*" + _RE_INMUEBLES.pattern + ")", re.I).search(
                bloque, m_cargo.end() if m_cargo else cabecera.end())
        if not m_act:
            continue
        # «Cargo: …» en la línea de encima del nombre (y no debajo)
        cargo_encima = ""
        if not m_cargo:
            encima = texto[:ini].rstrip(" \t").rsplit("\n", 1)[-1] if texto[ini:ini + 1] == "\n" else ""
            m_enc = re.match(r"\s*C[AÀ]R(?:GO|REC)\b\s*:?\s*(.+)", encima, re.I)
            cargo_encima = m_enc.group(1).strip() if m_enc else ""
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
            # desde el propio rótulo: a veces el importe va en su misma línea («II. Pasivo   350.000 €»)
            pasivo = _suma(bloque[m_pas.start():m_acd.start() if m_acd else len(bloque)])
        actividades = ""
        if m_acd:
            actividades = re.sub(r"\s+", " ", bloque[m_acd.end():]).strip(" .:…")
            # el texto de cierre del anuncio no es una actividad
            actividades = re.split(r"\b(?:Lo que se hace p[uú]blico|La qual cosa|Contra (?:el|la) presente|"
                                   r"En \w+, a \d|[A-ZÀ-Ý][\wà-ÿ' ]+, \d{1,2} d[e']\s*\w+ de 20\d\d)", actividades)[0].strip(" .,;")
            if i + 1 < len(inicios) and not m_cargo:
                actividades = re.split(r"(?:^|\s+)C[AÀ]R(?:GO|REC)\b\s*:?\s", actividades, flags=re.I)[0].strip(" .,;")
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
        elif cargo_encima:
            cargo = cargo_encima[:120]
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


_RE_PALABRA_CARGO = re.compile(r"ALCALD|BATLE|CONCEJAL|REGIDOR|TENIENTE|TINENT|PORTAVOZ|PORTAVEU|DIRECTOR|GERENT|"
                               r"SECRETAR|INTERVENTOR|TESORER|PRESIDENT|VOCAL\b|DIPUTAD", re.I)


def _leer_por_activo(texto: str) -> list[dict]:
    """Fichas sin rótulo «Titular»: el nombre y el cargo van sueltos justo encima
    de «I. Activo». Se parte por cada «Activo» y se mira hacia arriba."""
    anclas = list(_RE_ACTIVO.finditer(texto))
    res = []
    for k, a in enumerate(anclas):
        fin = anclas[k + 1].start() if k + 1 < len(anclas) else len(texto)
        cuerpo = texto[a.end():fin]
        m_pas = _RE_PASIVO.search(cuerpo)
        m_acd = _RE_ACTIVIDADES.search(cuerpo, m_pas.end() if m_pas else 0)
        activo = cuerpo[:(m_pas or m_acd).start() if (m_pas or m_acd) else len(cuerpo)]
        m_inm, m_otr = _RE_INMUEBLES.search(activo), _RE_OTROS.search(activo)
        m_tot = next((m for m in _RE_TOTAL.finditer(activo) if not m_otr or m.start() > m_otr.end()), None)
        if not (m_inm or m_otr):
            continue
        fin_inm = (m_otr or m_tot).start() if (m_otr or m_tot) else len(activo)
        inmuebles = _suma(activo[m_inm.end():fin_inm]) if m_inm else None
        otros = _suma(activo[m_otr.end():m_tot.start() if m_tot else len(activo)]) if m_otr else None
        # el total es solo lo que hay en su línea y la siguiente (debajo ya puede venir otra persona)
        total = _suma("\n".join(activo[m_tot.end():].split("\n")[:3])) if m_tot else None
        pasivo, actividades = None, ""
        if m_pas:
            trozo = cuerpo[m_pas.start():m_acd.start() if m_acd else len(cuerpo)]
            pasivo = _suma("\n".join(trozo.split("\n")[:6]) if not m_acd else trozo)
        if m_acd:
            # la actividad es lo que queda en la línea del rótulo (o, si está vacía, el párrafo siguiente)
            lineas = cuerpo[m_acd.end():].split("\n")
            actividades = lineas[0].strip(" .:…")
            if not actividades:
                actividades = next((l.strip(" .:…") for l in lineas[1:4] if l.strip()), "")
            actividades = re.sub(r"\s+", " ", re.sub(r"^\d+\s*[\.\-\)]\s*(?:Activi\w+)?", "", actividades)).strip()
        # cabecera: las líneas de encima de «Activo», hasta la ficha anterior
        encima = [l.strip() for l in texto[anclas[k - 1].end() if k else 0:a.start()].split("\n")]
        encima = [l for l in encima if l][-6:]
        nombre, cargo = "", []
        for l in reversed(encima):
            if _RE_PASIVO.match("\n" + l) or _RE_ACTIVIDADES.match("\n" + l) or _RE_TOTAL.search("\n" + l) or \
                    (_importes(l) and not re.match(r"\s*\d+\s*[\.\-\)ºª]", l)):
                break       # ya es la ficha de la persona anterior
            numerada = bool(re.match(r"\d+\s*[\.\-\)ºª]+", l))
            limpia = re.sub(r"^\d+\s*[\.\-\)ºª]+\s*", "", l)
            limpia = re.sub(r"^(?:Denominaci[oó]n?|C[aà]rrec|Cargo|Nom(?:bre)?(?: i cognoms| y apellidos)?|Titular)[^:]{0,40}:\s*", "",
                            limpia, flags=re.I)
            cortesia = re.match(r"(?:D\.?ª|DÑA\.?|DOÑA|DON|SRA?\.?|D\.)\s+", limpia, re.I)
            limpia = limpia[cortesia.end():] if cortesia else limpia
            limpia = limpia.strip(" .:-")
            if _RE_PALABRA_CARGO.search(limpia) and not cortesia:
                cargo.insert(0, limpia)
            elif _parece_nombre(limpia) and (not nombre or numerada or cortesia):
                nombre = limpia
            if numerada:
                break
        if not nombre:
            continue
        imp_act = _importes(actividades) if actividades and len(actividades) < 40 else []
        cuadra = None
        if total is not None and (inmuebles is not None or otros is not None):
            cuadra = abs((inmuebles or 0) + (otros or 0) - total) <= 1
        res.append({"nombre_completo": nombre, "cargo": " ".join(cargo)[:120], "inmuebles": inmuebles,
                    "otros_bienes": otros, "total_activo": total, "pasivo": pasivo,
                    "actividades": actividades[:400], "ingresos_actividades": round(sum(imp_act), 2) if imp_act else None,
                    "suma_cuadra": cuadra})
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
