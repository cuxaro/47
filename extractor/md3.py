"""Lee el formulario MD3 de Les Corts: «Registro de actividades, bienes e intereses».

Entrada: las páginas de un boletín ya convertidas en palabras y casillas
(ver `paginas.py`). Salida: una lista de declaraciones, cada una con:

    persona      nombre, apellidos, circunscripción, partido
    inmuebles    clave, tipo, % de dominio, provincia, valor catastral
    otros_bienes descripción, valor (vehículos, cuentas, acciones…)
    pasivo       descripción, valor (hipotecas, préstamos…)
    totales      los que escribe la propia persona

La declaración SOLO da la provincia de cada inmueble: no hay municipio,
dirección ni superficie.

Cómo se orienta el lector dentro del formulario:
  - los títulos de cada apartado («1.- Bienes inmuebles…», «3.- Pasivo»…)
    marcan dónde empieza y acaba cada tabla;
  - los recuadros (casillas) dan las filas y las columnas.
"""
from __future__ import annotations

import re

from .paginas import lineas
from .util import a_numero, a_porcentaje, a_provincia, norm, parecido

SALTO = 10_000  # separación vertical ficticia entre páginas de una declaración

RE_SELLO = re.compile(r"\bX[I1l]?\d{5,7}\b")
RE_FECHA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})\b")


# --------------------------------------------------------------------------- #
# 1. Trocear el boletín en declaraciones
# --------------------------------------------------------------------------- #
def _sello(pag: dict) -> tuple[str | None, str | None]:
    """Número y fecha del sello del registro de entrada de la página.

    Casi siempre el sello es texto del PDF. Cuando la página entera es una
    imagen, se lee del OCR (zona de arriba de la página).
    """
    fuentes = [" ".join(w["t"] for w in pag.get("sello") or [])]
    if pag.get("metodo") == "ocr":
        fuentes.append(" ".join(c["t"] for c in pag.get("casillas", []) if c["y1"] < 190))
        fuentes.append(" ".join(w["t"] for w in pag.get("palabras", []) if w["y1"] < 190))
    else:
        fuentes.append(" ".join(w["t"] for w in pag.get("palabras", [])))
    num = fecha = None
    for txt in fuentes:
        m = RE_SELLO.search(txt)
        if m and not num:
            num = re.sub(r"^X[1l](?=\d{6}$)", "XI", m.group(0))   # «X1000157» es «XI000157»
        f = RE_FECHA.search(txt)
        if f and not fecha:
            fecha = f"{f.group(3)}-{f.group(2)}-{f.group(1)}"
    return num, fecha


def _texto(pag: dict) -> str:
    return norm(" ".join(w["t"] for w in pag.get("palabras", []) if not w.get("v")))


def _es_portada_md3(pag: dict) -> bool:
    """¿Es la primera página de un formulario MD3? Lleva el título completo.

    (No basta con que aparezcan las palabras sueltas: el aviso de protección de
    datos de las demás páginas también habla de un «registro de actividades».)
    """
    t = _texto(pag)
    if "REGISTRO DE ACTIVIDADES BIENES E INTERESES" in t or "REGISTRE D ACTIVITATS BENS I INTERESSOS" in t:
        return True
    # OCR con erratas: basta con que una línea se parezca mucho al título
    for l in lineas(pag.get("palabras", []))[:40]:
        s = " ".join(w["t"] for w in l)
        if max(parecido(s, "REGISTRO DE ACTIVIDADES, BIENES E INTERESES"),
               parecido(s, "REGISTRE D'ACTIVITATS, BÉNS I INTERESSOS")) > 0.8:
            return True
    return False


def trocear(paginas: list[dict]) -> list[list[dict]]:
    """Agrupa las páginas en declaraciones MD3.

    Una declaración empieza en una portada MD3 y sigue mientras las páginas
    lleven el mismo sello de registro.
    """
    grupos, actual, sello_actual = [], None, None
    for pag in paginas:
        num, _ = _sello(pag)
        if _es_portada_md3(pag) and (num or pag["metodo"] == "ocr"):
            actual, sello_actual = [pag], num
            grupos.append(actual)
        elif actual is not None and num is not None and num == sello_actual:
            actual.append(pag)
        elif actual is not None and num is None and pag["metodo"] == "ocr" and actual[0]["metodo"] == "ocr":
            actual.append(pag)   # página escaneada a la que no se le lee el sello
        else:
            actual = None
    return grupos


# --------------------------------------------------------------------------- #
# 2. Preparar una declaración: todas sus páginas, una debajo de otra
# --------------------------------------------------------------------------- #
def _pulir(t: str) -> str:
    """Quita la basura que deja el OCR en los bordes de una casilla."""
    t = re.sub(r"\s+", " ", t).strip()
    for _ in range(3):
        t = re.sub(r"\s+[\|\[\]\(\)_—\-\.,:;'`\"<>=~]+$", "", t)          # signos sueltos al final
        if re.search(r"[A-ZÀ-Ý0-9]{2}", t):                                 # «PERUGA po» -> «PERUGA»
            t = re.sub(r"\s+(?:[a-zà-ÿñ]{1,2}|[ÑI\|]{1,2})$", "", t)
        t = re.sub(r"^[\|\[\]_—\-\.,:;'`\"<>=~]+\s*", "", t)
    if t.count("(") > t.count(")") and t.startswith("("):
        t = t[1:]
    return t.strip()


def _fluir(pags: list[dict]):
    """Pone todas las páginas una debajo de otra: (líneas, casillas)."""
    lins, cas = [], []
    for i, pag in enumerate(pags):
        dy = i * SALTO
        ocr = pag["metodo"] == "ocr"
        palabras = [w for w in pag.get("palabras", []) if not w.get("v")]
        for l in lineas(palabras):
            y0 = min(w["y0"] for w in l) + dy
            y1 = max(w["y1"] for w in l) + dy
            txt = " ".join(w["t"] for w in l)
            lins.append({"y0": y0, "y1": y1, "x0": l[0]["x0"], "t": txt, "n": norm(txt),
                         "palabras": l, "pag": pag["num"]})
        for c in pag.get("casillas", []):
            # fuera las casillas del sello (arriba a la derecha) y el pie
            if c["y1"] < 185 or c["y0"] > pag["alto"] - 95:
                continue
            n = {**c, "y0": c["y0"] + dy, "y1": c["y1"] + dy, "pag": pag["num"], "ocr": ocr}
            if ocr:
                n["t"] = _pulir(c["t"])
                # lecturas alternativas del mismo recuadro: la del OCR a tamaño
                # normal y la del OCR de la página entera
                alts = [_pulir(c["alt"])] if c.get("alt") else []
                dentro = [w for w in palabras if c["x0"] - 1 <= (w["x0"] + w["x1"]) / 2 <= c["x1"] + 1
                          and c["y0"] - 1 <= (w["y0"] + w["y1"]) / 2 <= c["y1"] + 1]
                if dentro and n["t"]:
                    alts.append(_pulir(" ".join(w["t"] for w in sorted(dentro, key=lambda w: w["x0"]))))
                n["alts"] = [a for a in alts if a and a != n["t"]]
                # «dudoso» = las dos lecturas del recuadro no dicen lo mismo
                if c.get("alt") is not None:
                    a, b = n["t"], _pulir(c["alt"])
                    va, vb = a_numero(a), a_numero(b)
                    n["dudoso"] = not (norm(a) == norm(b) or (va is not None and va == vb))
            else:
                n["t"] = c["t"].rstrip("+").strip() if c["t"].endswith("+") else c["t"]
                n["alts"] = []
            cas.append(n)
            if len(norm(n["t"])) >= 9 and (c["x1"] - c["x0"]) > 200:
                # un rótulo ancho («3.- PASIVO», «2.- BIENES Y DERECHOS…») también orienta
                lins.append({"y0": n["y0"], "y1": n["y1"], "x0": n["x0"], "t": n["t"], "n": norm(n["t"]),
                             "palabras": [], "pag": pag["num"], "rotulo": True})
    lins.sort(key=lambda l: l["y0"])
    cas.sort(key=lambda c: (c["y0"], c["x0"], -len(c["t"])))
    # algunos PDF dibujan el mismo recuadro dos veces: nos quedamos con uno
    unicas: list[dict] = []
    for c in cas:
        if any(abs(c["x0"] - u["x0"]) < 2.5 and abs(c["x1"] - u["x1"]) < 2.5
               and abs(c["y0"] - u["y0"]) < 2.5 and abs(c["y1"] - u["y1"]) < 2.5 for u in unicas[-12:]):
            continue
        unicas.append(c)
    return lins, unicas


def _ancla(lins: list[dict], *patrones: str, desde: float = -1, hasta: float = float("inf")) -> dict | None:
    """Primera línea entre `desde` y `hasta` cuyo texto normalizado casa con algún patrón."""
    for l in lins:
        if l["y0"] <= desde:
            continue
        if l["y0"] >= hasta:
            break
        if any(re.search(p, l["n"]) for p in patrones):
            return l
    return None


def _filas(cas: list[dict], y_ini: float, y_fin: float) -> list[list[dict]]:
    """Casillas entre dos alturas, agrupadas por fila."""
    dentro = [c for c in cas if y_ini <= (c["y0"] + c["y1"]) / 2 < y_fin]
    filas: list[list[dict]] = []
    for c in sorted(dentro, key=lambda c: ((c["y0"] + c["y1"]) / 2, c["x0"])):
        cy = (c["y0"] + c["y1"]) / 2
        if filas and abs(cy - sum((u["y0"] + u["y1"]) / 2 for u in filas[-1]) / len(filas[-1])) <= 4:
            filas[-1].append(c)
        else:
            filas.append([c])
    for f in filas:
        f.sort(key=lambda c: c["x0"])
    return filas


# --------------------------------------------------------------------------- #
# 3. Interpretar el contenido de las casillas
# --------------------------------------------------------------------------- #
_CLAVES = [("P", ("PLENO", "PLE", "PLENA", "PROPIEDAD", "PROPIETAT", "DOMINIO", "DOMINI")),
           ("N", ("NUDA", "NUA")), ("M", ("MULTIPROPIEDAD", "MULTIPROPIETAT")),
           ("U", ("USUFRUCTO", "USDEFRUIT", "USUFRUIT"))]
_TIPOS = [("V", ("VIVIENDA", "VIVENDA", "HABITATGE", "PISO", "PIS", "CASA", "APARTAMENTO", "CHALET", "ADOSADO")),
          ("L", ("LOCAL", "LOCALES", "LOCALS", "OFICINA", "NAVE")),
          ("R", ("RUSTICO", "RUSTICA", "RUSTIC", "RUSTICS", "RUSTICOS", "FINCA", "TERRENO", "PARCELA", "HUERTO")),
          ("O", ("OTROS", "ALTRES", "GARAJE", "GARATGE", "PLAZA", "TRASTERO", "SOLAR", "URBANO", "URBANA"))]
# letras que el OCR confunde cuando la casilla solo tiene una
_CONFUSION_TIPO = {"Y": "V", "0": "O", "Q": "O", "D": "O", "U": "V", "K": "R"}
_CONFUSION_CLAVE = {"F": "P", "D": "P"}


def _codigo1(txt: str, tabla, validos: str, confusion: dict, ocr: bool) -> str | None:
    n = norm(txt)
    if not n:
        return None
    for cod, palabras in tabla:
        if any(re.search(rf"\b{p}\b", n) for p in palabras):
            return cod
    letras = n.replace(" ", "")
    if len(letras) <= 2:
        c = letras[0]
        if c in validos:
            return c
        if ocr and c in confusion:
            return confusion[c]
        if c == "0" and "O" in validos:
            return "O"
    return None


def _codigo(c: dict, tabla, validos: str, confusion: dict) -> str | None:
    for t in [c["t"], *c.get("alts", [])]:
        cod = _codigo1(t, tabla, validos, confusion, c.get("ocr", False))
        if cod:
            return cod
    return None


def _categoria(desc: str) -> str:
    n = norm(desc)
    reglas = [
        ("pensiones", r"PENSION|JUBILACI|EPSV"),
        ("cuentas", r"CUENTA|COMPTE|\bCC\b|\bCTA\b|PLAZO|IMPOSICI|SALDO|CORRIENTE|CORRENT|AHORRO|ESTALVI|DEPOSITO|DEPOSIT|DIPOSIT|LIBRETA|BANC|CAIXA|CAJA|EFECTIVO|EFECTIU|IPF|IBERCAJA|OPENBANK|\bING\b|BBVA|SANTANDER|SABADELL|CAJAMAR|UNICAJA|KUTXA|ABANCA|BANKINTER"),
        ("inversiones", r"ACCION|ACCIO|FONDO|FONS|PARTICIPACI|VALORES|VALORS|BOLSA|BORSA|INVERSI|LETRAS|LLETRES|DEUDA PUBLICA|BONOS|SOCIEDAD|SOCIETAT|\bS L\b|\bSL\b|\bSA\b|CAPITAL SOCIAL|CRIPTO|BITCOIN|\bCB\b|COMUNIDAD DE BIENES"),
        ("seguros", r"SEGURO|ASSEGURAN"),
        ("vehiculos", r"VEHICUL|VEHICLE|COCHE|COTXE|TURISMO|TURISME|MOTO|FURGON|AUTOMOVIL|AUTOMOBIL|REMOLQUE|CARAVANA|BARCO|EMBARCACI"
                      r"|SEAT|RENAULT|PEUGEOT|CITROEN|FORD|OPEL|VOLKSWAGEN|\bVW\b|AUDI|BMW|MERCEDES|TOYOTA|NISSAN|HYUNDAI|\bKIA\b"
                      r"|SKODA|VOLVO|FIAT|DACIA|MAZDA|HONDA|\bMINI\b|TESLA|LEXUS|JEEP|SUZUKI|YAMAHA|VESPA|PIAGGIO|MITSUBISHI|SMART"
                      r"|CUPRA|LAND ROVER|PORSCHE|JAGUAR|ALFA ROMEO|SSANGYONG|SSNAGYONG|\bMG\b|SUBARU|CHEVROLET|KAWASAKI|DUCATI"),
    ]
    for cat, pat in reglas:
        if re.search(pat, n):
            return cat
    return "otros"


def _tipo_pasivo(desc: str) -> str:
    n = norm(desc)
    if re.search(r"HIPOTEC", n):
        return "hipoteca"
    if re.search(r"PRES\w?TAMO|PRESTEC|PTMO|CREDITO|CREDIT|CRECITO|LEASING|RENTING|FINANC|POLIZA", n):
        return "prestamo"
    if re.search(r"TARJETA|TARGETA", n):
        return "tarjeta"
    if re.search(r"CUENTA|COMPTE", n):
        return "cuenta"
    return "otros"


def _es_etiqueta(txt: str) -> bool:
    etiquetas = ("Descripción", "Descripció", "Valor (euros)", "Clave (*)", "Tipo (**)",
                 "Situación (provincia)", "Valor catastral", "Valor catastral del conjunto",
                 "Valor global conjunto")
    return any(parecido(txt, e) > 0.72 for e in etiquetas)


def _hay_palabra(txt: str) -> bool:
    """¿Tiene al menos una palabra de verdad? (para descartar ruido del escáner)"""
    for tok in re.findall(r"[A-Za-zÀ-ÿ]{3,}", txt):
        letras = norm(tok)
        if len(set(letras)) >= 2 and re.search(r"[AEIOU]", letras) and re.search(r"[^AEIOU]", letras):
            return True
    return False


def _cabecera(lins, y_ini, y_fin, patron) -> float:
    """Altura donde acaba la cabecera de una tabla (o y_ini si no se encuentra)."""
    ys = [l["y1"] for l in lins if y_ini <= l["y0"] < y_fin and re.search(patron, l["n"])
          and "CONJUNT" not in l["n"] and l["y1"] - y_ini < 60]
    return max(ys) if ys else y_ini


def _cuadrar(items: list[dict], campo: str, total: float | None) -> bool | None:
    """Comprueba que la suma de las líneas da el total declarado.

    - Hay quien pone como total la suma de los valores, y quien pone solo la
      parte que le toca (valor × % de dominio). Valen las dos.
    - Si no cuadra y alguna casilla tenía lecturas alternativas del OCR, prueba
      con ellas: la que hace cuadrar la suma es la buena.
    Devuelve True/False, o None si no hay con qué comparar.
    """
    if total is None or not items or any(i[campo] is None for i in items):
        return None

    def cuadra() -> bool:
        if abs(sum(i[campo] for i in items) - total) <= 1:
            return True
        if all(i.get("porcentaje") is not None for i in items):
            return abs(sum(i[campo] * i["porcentaje"] / 100 for i in items) - total) <= 1
        return False

    if cuadra():
        return True
    for i in items:
        original = i[campo]
        for alt in i.get("_alts", []):
            v = a_numero(alt)
            if v is None:
                continue
            i[campo] = v
            if cuadra():
                i["valor_txt"], i["dudoso"], i["corregido"] = alt, False, True
                return True
        i[campo] = original
    return False


def aplicar_correccion(d: dict, c: dict) -> dict:
    """Sustituye lo leído por una transcripción hecha a mano (ver correcciones/)."""
    d["persona"] = {**d["persona"], **c.get("persona", {})}
    if "inmuebles" not in c:      # corrección solo del nombre
        d.setdefault("notas", []).append(c.get("motivo", "Nombre corregido a mano"))
        return d
    d["inmuebles"] = [{"clave": i.get("clave"), "clave_txt": i.get("clave") or "", "tipo": i.get("tipo"),
                       "tipo_txt": i.get("tipo") or "", "porcentaje": i.get("porcentaje"),
                       "porcentaje_txt": "", "provincia": i.get("provincia"), "provincia_txt": i.get("provincia") or "",
                       "valor_catastral": i.get("valor_catastral"), "valor_txt": "", "pagina": d["paginas"][0],
                       "dudoso": False} for i in c.get("inmuebles", [])]
    d["otros_bienes"] = [{"descripcion": i["descripcion"], "valor": i.get("valor"), "valor_txt": "",
                          "pagina": d["paginas"][0], "dudoso": False, "categoria": _categoria(i["descripcion"])}
                         for i in c.get("otros_bienes", [])]
    d["pasivo"] = [{"descripcion": i["descripcion"], "valor": i.get("valor"), "valor_txt": "",
                    "pagina": d["paginas"][0], "dudoso": False, "categoria": _tipo_pasivo(i["descripcion"])}
                   for i in c.get("pasivo", [])]
    for k in ("total_catastral", "total_otros_bienes", "total_pasivo"):
        d[k] = c.get(k)
    d["suma_inmuebles_cuadra"] = _cuadrar(d["inmuebles"], "valor_catastral", d["total_catastral"])
    d["suma_otros_cuadra"] = _cuadrar(d["otros_bienes"], "valor", d["total_otros_bienes"])
    d["suma_pasivo_cuadra"] = _cuadrar(d["pasivo"], "valor", d["total_pasivo"])
    d["metodo"], d["ilegible"], d["totales_repetidos"] = "manual", False, []
    d["avisos"], d["notas"] = [], [c.get("motivo", "Transcrita a mano del original")]
    return d


# --------------------------------------------------------------------------- #
# 4. Leer una declaración
# --------------------------------------------------------------------------- #
def _persona(lins, cas, y_fin, ocr: bool) -> dict:
    """Nombre, apellidos, circunscripción y partido de la portada."""
    p = {"nombre": None, "apellidos": None, "circunscripcion": None, "partido": None}

    def tras(ws, toks, ini, fin=None):
        return " ".join(w["t"] for w in ws[ini:fin]).strip() or None

    # a) formularios digitales: el valor va en la misma línea que su etiqueta
    for l in ([] if ocr else lins):
        if l["y0"] > y_fin:
            break
        ws = l["palabras"]
        toks = [norm(w["t"]) for w in ws]
        for e_nom, e_ape in (("NOM", "COGNOMS"), ("NOMBRE", "APELLIDOS")):
            if e_nom in toks and e_ape in toks:
                i, j = toks.index(e_nom), toks.index(e_ape)
                p["nombre"] = p["nombre"] or tras(ws, toks, i + 1, j)
                p["apellidos"] = p["apellidos"] or tras(ws, toks, j + 1)
        if toks[:2] in (["CIRCUMSCRIPCIO", "ELECTORAL"], ["CIRCUNSCRIPCION", "ELECTORAL"]) and len(ws) > 2:
            p["circunscripcion"] = p["circunscripcion"] or tras(ws, toks, 2)
        for e in ("ELECCIONS", "ELECCIONES"):
            if e in toks and toks[0] in ("PARTIT", "PARTIDO"):
                p["partido"] = p["partido"] or tras(ws, toks, toks.index(e) + 1)

    # b) formularios escaneados: las casillas de la portada, por posición
    if not p["nombre"] or not p["apellidos"]:
        tit = _ancla(lins, r"REGISTR[OE] D ?E? ?ACTIVI", r"BIENES E INTERES", r"BENS I INTERESSOS")
        dat = _ancla(lins, r"DAD?ES PERSONALS", r"DATOS PERSONALES", desde=tit["y0"] if tit else -1)
        y0 = dat["y1"] if dat else (tit["y1"] if tit else 0)
        ruido = r"DECLARA|PRIMERA|MODIFICACI|FINALI|LEGISLATURA|REGISTR|DADES PERSONALS|DATOS PERSONALES"
        filas = [[c for c in f if c["t"] and not _es_etiqueta(c["t"]) and not re.search(ruido, norm(c["t"]))]
                 for f in _filas(cas, y0, min(y_fin, y0 + 80 if dat else y_fin))]
        filas = [f for f in filas if f]
        if filas:
            for c in filas[0]:
                k = "nombre" if c["x0"] < 250 else "apellidos"
                p[k] = p[k] or c["t"]
        if len(filas) > 1:
            p["circunscripcion"] = p["circunscripcion"] or filas[1][0]["t"]
        if len(filas) > 2:
            p["partido"] = p["partido"] or filas[2][0]["t"]

    # c) último recurso: la línea «NOMBRE … APELLIDOS …» leída por el OCR de página.
    #    Las etiquetas salen mal, pero los datos van en mayúsculas y se leen bien.
    if ocr and (not p["nombre"] or not p["apellidos"]):
        dat = _ancla(lins, r"DAD?ES PERSONALS", r"DATOS PERSONALES")
        candidatas = [l for l in lins if not l.get("rotulo") and dat and dat["y1"] - 2 < l["y0"] < dat["y1"] + 22
                      and "PERSONAL" not in l["n"]]
        for l in candidatas:
            tramos, actual = [], []
            for tok in l["t"].split():
                limpio = re.sub(r"[^A-Za-zÀ-ÿ]", "", tok)
                es_dato = len(limpio) >= 2 and limpio.isupper() and not any(
                    parecido(limpio, e) > 0.7 for e in ("NOMBRE", "NOM", "APELLIDOS", "COGNOMS"))
                if es_dato:
                    actual.append(limpio)
                elif actual:
                    tramos.append(" ".join(actual))
                    actual = []
            if actual:
                tramos.append(" ".join(actual))
            if len(tramos) >= 2:
                p["nombre"] = p["nombre"] or tramos[0]
                p["apellidos"] = p["apellidos"] or " ".join(tramos[1:])
                break
            if len(tramos) == 1 and p["apellidos"] and not p["nombre"] and parecido(tramos[0], p["apellidos"]) < 0.6:
                p["nombre"] = tramos[0]
                break
    if ocr and not p["circunscripcion"]:
        l = _ancla(lins, r"ELECTORAL")
        if l:
            p["circunscripcion"] = a_provincia(l["t"])
    prov = a_provincia(p["circunscripcion"])
    if prov in ("Alicante", "Castellón", "Valencia"):
        p["circunscripcion"] = prov
    return p


def leer_declaracion(pags: list[dict]) -> dict:
    lins, cas = _fluir(pags)
    sello, fecha = _sello(pags[0])
    sello = sello or f"sin-sello-p{pags[0]['num']}"
    fin = (len(pags) + 1) * SALTO

    a_act = _ancla(lins, r"DECLARACI\w* D ?E? ?ACTIVI")
    a_inm = _ancla(lins, r"\b1 \w{3,7} (INMUEBLES|IMMOBLES)", r"(INMUEBLES|IMMOBLES) URBAN")
    y_inm = a_inm["y0"] if a_inm else None
    a_noinm = _ancla(lins, r"NATURALE[SZ]A ?NO I[NM]MOBILI", r"DERECHOS DE ?NATUR", r"DRETS DE NATUR",
                     r"NO INMOBILIARIA", r"NO IMMOBILIARIA", desde=y_inm or -1)
    y_noinm = a_noinm["y0"] if a_noinm else None
    a_pas = _ancla(lins, r"\b3 (PASIVO|PASSIU)", r"^\W*(\w\s+)?(PASIVO|PASSIU)\b", desde=y_noinm or y_inm or -1)
    y_pas = a_pas["y0"] if a_pas else None
    a_fin = _ancla(lins, r"ESTOS DATOS SE DEBERAN", r"AQUESTES DADES CALDRA", r"DECLARO? QUE L[OE]S DA",
                   r"PROTECCIO DE DADES", r"PROTECCION DE DATOS",
                   desde=y_pas or y_noinm or y_inm or -1)
    y_fin = a_fin["y0"] if a_fin else fin

    ocr = pags[0]["metodo"] == "ocr"
    d = {
        "sello": sello, "fecha_registro": fecha,
        "paginas": [p["num"] for p in pags],
        "metodo": "ocr" if any(p["metodo"] == "ocr" for p in pags) else "texto",
        "persona": _persona(lins, cas, a_act["y0"] if a_act else (y_inm or fin), ocr=ocr),
        "inmuebles": [], "otros_bienes": [], "pasivo": [],
        "total_catastral": None, "total_otros_bienes": None, "total_pasivo": None,
        "avisos": [],   # problemas al leer: conviene revisar a mano
        "notas": [],    # peculiaridades de lo que la persona escribió (no son errores de lectura)
    }
    if y_inm is None:
        d["avisos"].append("No se ha encontrado el apartado de bienes inmuebles")
        return d

    # ---- 1. Inmuebles -------------------------------------------------------
    y1 = y_noinm or y_pas or y_fin
    a_tot1 = _ancla(lins, r"(CATASTRAL|CADASTRAL|CATASIRAL) DEL CONJU", desde=y_inm, hasta=y1)
    cab = _cabecera(lins, y_inm, y1, r"SITUACI|PROVINCI|CATASTRAL|CADASTRAL")
    y_tot1 = a_tot1["y0"] if a_tot1 else None
    for fila in _filas(cas, cab - 2, y_tot1 - 3 if y_tot1 else y1):
        if len(fila) < 4 or not any(c["t"] for c in fila):
            continue
        if sum(_es_etiqueta(c["t"]) for c in fila if c["t"]) >= 2:
            continue
        if len(fila) != 5:
            d["avisos"].append("Fila de inmuebles con un número raro de casillas")
            continue
        clave, tipo, pct, prov, valor = fila
        cod_c = _codigo(clave, _CLAVES, "PNMU", _CONFUSION_CLAVE)
        cod_t = _codigo(tipo, _TIPOS, "VLOR", _CONFUSION_TIPO)
        if cod_c is None or cod_t is None:
            # hay quien rellena las dos primeras columnas al revés
            alt_c = _codigo(tipo, _CLAVES, "PNMU", {})
            alt_t = _codigo(clave, _TIPOS, "VLOR", {})
            if alt_c and alt_t:
                cod_c, cod_t = alt_c, alt_t
        validos = sum(x is not None for x in (cod_c, cod_t, a_porcentaje(pct["t"]), a_provincia(prov["t"]),
                                              a_numero(valor["t"])))
        if validos < (2 if clave.get("ocr") else 1):
            continue  # fila vacía con ruido del escáner
        d["inmuebles"].append({
            "clave": cod_c, "clave_txt": clave["t"], "tipo": cod_t, "tipo_txt": tipo["t"],
            "porcentaje": a_porcentaje(pct["t"]), "porcentaje_txt": pct["t"],
            "provincia": a_provincia(prov["t"]), "provincia_txt": prov["t"],
            "valor_catastral": a_numero(valor["t"]), "valor_txt": valor["t"],
            "pagina": clave["pag"], "_alts": valor.get("alts", []),
            "dudoso": any(bool(c.get("dudoso")) for c in (pct, prov, valor) if c["t"]),
        })
    if a_tot1:
        cands = [c for c in cas if a_tot1["y0"] - 8 <= (c["y0"] + c["y1"]) / 2 <= a_tot1["y1"] + 10
                 and c["x0"] > a_tot1["x0"] + 40 and c["x1"] - c["x0"] > 120   # la casilla del total es ancha
                 and a_numero(c["t"]) is not None]
        if cands:
            d["total_catastral"] = a_numero(cands[0]["t"])
    if d["total_catastral"] is None:
        # El OCR no siempre lee el rótulo «Valor catastral del conjunto»: el total es
        # la casilla ancha y suelta que queda justo debajo de las filas de inmuebles.
        ult = max((c["y1"] for c in cas if cab <= c["y0"] < y1 and c["x1"] - c["x0"] < 120), default=cab)
        for fila in _filas(cas, ult - 2, y1):
            c = fila[0]
            if len(fila) == 1 and c["x1"] - c["x0"] > 120 and c["y1"] - c["y0"] < 30 \
                    and a_numero(c["t"]) is not None and not _hay_palabra(c["t"]):
                d["total_catastral"] = a_numero(c["t"])
                break

    # ---- 2 y 3. Otros bienes y pasivo ---------------------------------------
    def tabla(y_ini, y_end, destino, clave_total, clasifica):
        cab = _cabecera(lins, y_ini, y_end, r"DESCRIP")
        todas = [c for f in _filas(cas, y_ini - 12, y_end) for c in f]
        margen = min((c["x0"] for c in todas), default=None)
        for fila in _filas(cas, cab - 2, y_end):
            if not any(c["t"] for c in fila):
                continue
            if margen is not None and fila[0]["x0"] > margen + 30:
                # casilla desplazada a la derecha de su etiqueta: es el total
                for c in fila:
                    v = a_numero(c["t"])
                    if v is not None and d[clave_total] is None and not _hay_palabra(c["t"]):
                        d[clave_total] = v
                        return  # después del total ya no hay más filas de esta tabla
                continue
            if len(fila) != 2:
                continue
            desc, val = fila
            if _es_etiqueta(desc["t"]) or (not desc["t"] and _es_etiqueta(val["t"])):
                continue
            if desc["x1"] - desc["x0"] > 0.85 * (val["x1"] - desc["x0"]):
                continue  # recuadro de texto, no una fila de la tabla
            v = a_numero(val["t"])
            if not _hay_palabra(desc["t"]) and (v is None or val.get("dudoso")):
                continue  # fila vacía con ruido del escáner
            if v is None and desc.get("ocr") and not re.search(r"[A-Za-zÀ-ÿ]{4,}", desc["t"]):
                continue  # ídem: sin importe y sin una palabra larga
            if v is None and len(desc["t"].split()) <= 1 and (
                    _hay_palabra(val["t"]) or parecido(desc["t"], "Descripcion") > 0.5):
                continue  # la cabecera «Descripción | Valor (euros)» mal leída
            item = {"descripcion": desc["t"] if _hay_palabra(desc["t"]) or re.search(r"\d", desc["t"]) else "",
                    "valor": v, "valor_txt": val["t"], "pagina": desc["pag"],
                    "dudoso": bool(val.get("dudoso")), "_alts": val.get("alts", [])}
            item.update(clasifica(item["descripcion"]))
            d[destino].append(item)

    if y_noinm is not None:
        tabla(y_noinm, y_pas or y_fin, "otros_bienes", "total_otros_bienes",
              lambda t: {"categoria": _categoria(t)})
    else:
        d["avisos"].append("No se ha encontrado el apartado de bienes no inmobiliarios")
    if y_pas is not None:
        tabla(y_pas, y_fin, "pasivo", "total_pasivo", lambda t: {"categoria": _tipo_pasivo(t)})
    else:
        d["avisos"].append("No se ha encontrado el apartado de pasivo")

    # ---- Comprobaciones -----------------------------------------------------
    d["suma_inmuebles_cuadra"] = _cuadrar(d["inmuebles"], "valor_catastral", d["total_catastral"])
    d["suma_otros_cuadra"] = _cuadrar(d["otros_bienes"], "valor", d["total_otros_bienes"])
    d["suma_pasivo_cuadra"] = _cuadrar(d["pasivo"], "valor", d["total_pasivo"])
    for k, cuadra in (("inmuebles", "suma_inmuebles_cuadra"), ("otros_bienes", "suma_otros_cuadra"),
                      ("pasivo", "suma_pasivo_cuadra")):
        for i in d[k]:
            i.pop("_alts", None)
            if d[cuadra]:
                i["dudoso"] = False  # la suma da el total declarado: los importes están bien leídos
    # Formularios escritos a mano: el OCR no los lee. Se nota porque casi ninguna
    # casilla se lee igual las dos veces.
    todos = [i for k in ("inmuebles", "otros_bienes", "pasivo") for i in d[k]]
    comprobada = any(d[k] for k in ("suma_inmuebles_cuadra", "suma_otros_cuadra", "suma_pasivo_cuadra"))
    d["ilegible"] = bool(d["metodo"] == "ocr" and len(todos) >= 3 and not comprobada
                         and sum(1 for i in todos if i.get("dudoso")) / len(todos) >= 0.5)
    if d["ilegible"]:
        d["avisos"].append("Formulario escrito a mano o muy borroso: el OCR no es fiable")
    # Totales repetidos sin detalle: casi seguro un despiste al rellenar.
    tc, to, tp = d["total_catastral"], d["total_otros_bienes"], d["total_pasivo"]
    d["totales_repetidos"] = []
    if to is not None and not d["otros_bienes"] and to == tc:
        d["totales_repetidos"].append("total_otros_bienes")
        d["notas"].append("El total de otros bienes repite el valor catastral y no tiene detalle: no se cuenta")
    if tp is not None and not d["pasivo"] and tp in (to, tc):
        d["totales_repetidos"].append("total_pasivo")
        d["notas"].append("El total de deudas repite el de otro apartado y no tiene detalle: no se cuenta")
    for i in d["pasivo"]:
        if i["categoria"] in ("cuenta", "otros") and _categoria(i["descripcion"]) in ("cuentas", "pensiones", "vehiculos"):
            i["categoria"] = "posible_bien"
    if any(i["categoria"] == "posible_bien" for i in d["pasivo"]):
        d["notas"].append("Hay cuentas u otros bienes anotados en el apartado de deudas (se mantienen como están declarados)")
    return d


def leer_boletin(paginas: list[dict]) -> list[dict]:
    return [leer_declaracion(g) for g in trocear(paginas)]
