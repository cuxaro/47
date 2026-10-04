"""Fuente: Butlletí Oficial de la Província de València (BOP).

Aquí publican sus declaraciones los ayuntamientos y la Diputación de la
provincia de Valencia (art. 131 de la Ley 8/2010 y Decreto 191/2010).

La web del BOP es una aplicación con sesión (JSF/PrimeFaces): no hay direcciones
directas a cada anuncio. Hay que hacer lo mismo que una persona:

    1. abrir la portada (da una sesión y un formulario de búsqueda);
    2. buscar por palabras y fechas;
    3. abrir cada anuncio de la lista y, si tiene anexos en PDF, descargarlos.

Todo se guarda en .cache/bopv/ para no volver a pedirlo.
"""
from __future__ import annotations

import datetime as dt
import html
import http.cookiejar
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

from .red import AGENTE, PAUSA

PORTADA = "https://bop.dival.es/bop/"
# El buscador exige que estén todas las palabras de la consulta y no distingue
# acentos; cada ayuntamiento titula el anuncio a su manera, así que se prueban varias.
CONSULTAS = ["declaraciones bienes", "declaracion bienes", "declaracions bens", "declaracio bens",
             "registro intereses", "registre interessos"]
POR_PAGINA = 25                            # resultados que muestra la lista
# El sumario tiene que hablar de declaraciones de bienes (en castellano o valenciano)
RE_SUMARIO = re.compile(r"declaraci\w+.{0,80}?\b(bienes|b[eé]ns)\b|\b(bienes|b[eé]ns)\b.{0,80}?declaraci"
                        r"|regist\w+ d['e ]*\s*interes", re.I | re.S)
# …y no de otra cosa que use las mismas palabras
RE_NO_SUMARIO = re.compile(r"inter[eé]s cultural|rellev[aà]ncia local|relevancia local|bienes inmuebles municipales|"
                           r"inventari|subhasta|subasta|alienaci|enajenaci|expropia|utilitat p[uú]blica|utilidad p[uú]blica", re.I)


def _log(*a):
    print(*a, file=sys.stderr, flush=True)


class Sesion:
    """Una visita al BOP: mantiene las cookies y el «estado de la vista» de JSF."""

    def __init__(self):
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.op.addheaders = [("User-Agent", AGENTE), ("Accept-Language", "es,ca;q=0.8")]
        self._ultima = 0.0
        r = self._abrir(PORTADA)
        pagina = r.read().decode("utf-8", "replace")
        self.base = r.geturl()
        m = re.search(r'<form id="([^"]+)"[^>]*action="([^"]+)"[^>]*>(?:(?!</form>).)*?name="buscador"(?:(?!</form>).)*?</form>',
                      pagina, re.S)
        if not m:
            raise RuntimeError("No se encuentra el formulario de búsqueda del BOP de Valencia")
        self.form_id, self.accion = m.group(1), html.unescape(m.group(2))
        self.campos = {}
        for tag in re.findall(r"<(?:input|select|textarea)[^>]*>", m.group(0)):
            n = re.search(r'name="([^"]+)"', tag)
            v = re.search(r'value="([^"]*)"', tag)
            t = re.search(r'type="([^"]+)"', tag)
            if n and (not t or t.group(1) not in ("submit", "checkbox", "button")):
                self.campos[n.group(1)] = html.unescape(v.group(1)) if v else ""
        self.vista = self.campos.get("javax.faces.ViewState", "")
        self.form_lista = None
        self._resultado = ""

    def _abrir(self, url, datos=None, cabeceras=None):
        espera = PAUSA - (time.time() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        self._ultima = time.time()
        cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
        return self.op.open(urllib.request.Request(url, data=cuerpo, headers=cabeceras or {}), timeout=120)

    def _ajax(self, datos: dict) -> str:
        datos = {**datos, "javax.faces.partial.ajax": "true", "javax.faces.partial.execute": "@all"}
        r = self._abrir(urllib.parse.urljoin(self.base, self.accion), datos, {
            "Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
        x = r.read().decode("utf-8", "replace")
        m = re.search(r'ViewState:0"><!\[CDATA\[(.*?)\]\]>', x)
        if m:
            self.vista = m.group(1)
        return x

    def buscar(self, texto: str, ini: dt.date, fin: dt.date) -> tuple[list[dict], int]:
        """Busca anuncios entre dos fechas. Devuelve (los de la primera página, total)."""
        d = dict(self.campos)
        d.update({"buscador": texto, "filtroCalendarioIni_input": ini.strftime("%d/%m/%Y"),
                  "filtroCalendarioFin_input": fin.strftime("%d/%m/%Y"),
                  "javax.faces.ViewState": self.vista, "javax.faces.source": "buscarBtn",
                  "javax.faces.partial.render": "messages boletines3 edictos",
                  "buscarBtn": "buscarBtn", self.form_id: self.form_id})
        x = self._ajax(d)
        self._resultado = x
        m = re.search(r"rowCount:(\d+)", x)
        total = int(m.group(1)) if m else 0
        f = re.search(r"PrimeFaces\.ab\(\{s:&quot;list:\d+:[^&]+&quot;,f:&quot;([^&]+)&quot;", x)
        self.form_lista = f.group(1) if f else None
        return _resultados(x), total

    def abrir(self, fila: dict) -> str:
        """Abre un anuncio de la última búsqueda. Devuelve su HTML."""
        x = self._ajax({self.form_lista: self.form_lista, "javax.faces.ViewState": self.vista,
                        "javax.faces.source": fila["_boton"], "javax.faces.partial.render": "dlgHTML",
                        fila["_boton"]: fila["_boton"]})
        m = re.search(r'<update id="dlgHTML"><!\[CDATA\[(.*?)\]\]></update>', x, re.S)
        return m.group(1) if m else ""

    def anexos(self, anuncio_html: str) -> list[tuple[str, bytes]]:
        """Descarga los anexos (PDF) del anuncio que se acaba de abrir."""
        f = re.search(r'<form id="([^"]+)"', anuncio_html)
        res = []
        for boton, nombre in re.findall(
                r"addSubmitParam\('[^']+',\{'([^']+)':'[^']+'\}\)\.submit\('[^']+'\);return false;\">(?:<span[^>]*></span>)?([^<]+)</a>",
                anuncio_html):
            if not f:
                break
            r = self._abrir(urllib.parse.urljoin(self.base, self.accion),
                            {f.group(1): f.group(1), boton: boton, "javax.faces.ViewState": self.vista})
            cuerpo = r.read()
            if cuerpo[:4] == b"%PDF":
                res.append((html.unescape(nombre).strip(), cuerpo))
        return res


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def _resultados(x: str) -> list[dict]:
    """Saca de la respuesta la lista de anuncios: entidad, sumario, registro, fecha."""
    m = re.search(r'<update id="edictos"><!\[CDATA\[(.*?)\]\]></update>', x, re.S)
    if not m:
        return []
    cuerpo = m.group(1)
    res = []
    for i in sorted({int(n) for n in re.findall(r'id="list:(\d+):', cuerpo)}):
        trozo = cuerpo[cuerpo.find(f'id="list:{i}:'):]
        sig = trozo.find(f'id="list:{i + 1}:')
        trozo = trozo[:sig] if sig > 0 else trozo
        ent = re.search(r'class="[^"]*\bentidad\b[^"]*"[^>]*>\s*<div[^>]*>(.*?)</div>', trozo, re.S)
        sec = re.search(r'class="[^"]*\bseccion\b[^"]*"[^>]*>\s*<div[^>]*>(.*?)</div>', trozo, re.S)
        sumario = re.search(r'class="sumario">(.*?)</div>', trozo, re.S)
        boton = re.search(r'id="(list:%d:[^"]+)"[^>]*aria-label="Vore HTML"' % i, trozo)
        info = _texto(trozo)
        reg = re.search(r"\b(\d{4}/\d{2,6})\b", info[info.find("registre"):] if "registre" in info else info)
        fecha = re.search(r"(\d{2})/(\d{2})/(\d{4})", info)
        if not (boton and reg):
            continue
        res.append({
            "registro": reg.group(1), "entidad": _texto(ent.group(1)) if ent else "",
            "seccion": _texto(re.sub(r"<a.*?</a>", "", sec.group(1), flags=re.S)) if sec else "",
            "sumario": _texto(sumario.group(1)) if sumario else "",
            "fecha": f"{fecha.group(3)}-{fecha.group(2)}-{fecha.group(1)}" if fecha else None,
            "_boton": boton.group(1),
        })
    return res


def _ventanas(desde: dt.date, hasta: dt.date, dias: int = 92):
    d = desde
    while d <= hasta:
        f = min(d + dt.timedelta(days=dias - 1), hasta)
        yield d, f
        d = f + dt.timedelta(days=1)


def recoger(cache: pathlib.Path, desde: dt.date, hasta: dt.date | None = None,
            limite: int | None = None) -> list[dict]:
    """Recorre el BOP por meses y guarda cada anuncio de declaraciones de bienes.

    Devuelve el índice: una ficha por anuncio (registro, entidad, sumario, fecha,
    ficheros). Lo ya descargado no se vuelve a pedir; los meses cerrados hace
    más de 45 días tampoco se vuelven a buscar.
    """
    cache.mkdir(parents=True, exist_ok=True)
    f_indice = cache / "indice.json"
    estado = json.loads(f_indice.read_text(encoding="utf-8")) if f_indice.exists() else {"anuncios": {}, "ventanas": []}
    hasta = hasta or dt.date.today()
    sesion, nuevos = None, 0

    def guardar():
        f_indice.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")

    pendientes = [(q, ini, fin) for q in CONSULTAS for ini, fin in _ventanas(desde, hasta)]
    while pendientes:
        consulta, ini, fin = pendientes.pop(0)
        clave = f"{consulta}|{ini}:{fin}"
        if clave in estado["ventanas"]:
            continue
        if sesion is None:
            sesion = Sesion()
        filas, total = sesion.buscar(consulta, ini, fin)
        if total > POR_PAGINA and fin > ini:
            # demasiados resultados para una página: partir el periodo en dos
            medio = ini + (fin - ini) // 2
            pendientes[:0] = [(consulta, ini, medio), (consulta, medio + dt.timedelta(days=1), fin)]
            continue
        if total:
            _log(f"  BOP València «{consulta}» {ini} → {fin}: {total} anuncios")
        for fila in filas:
            if not RE_SUMARIO.search(fila["sumario"]) or RE_NO_SUMARIO.search(fila["sumario"]):
                continue
            reg = fila["registro"]
            if reg in estado["anuncios"]:
                continue
            nombre = reg.replace("/", "-")
            cuerpo = sesion.abrir(fila)
            if not cuerpo or "no trobat" in cuerpo:
                _log(f"    {reg}: no se ha podido abrir")
                continue
            (cache / f"{nombre}.html").write_text(cuerpo, encoding="utf-8")
            ficheros = []
            for k, (nom_anexo, pdf) in enumerate(sesion.anexos(cuerpo)):
                (cache / f"{nombre}.a{k}.pdf").write_bytes(pdf)
                ficheros.append({"fichero": f"{nombre}.a{k}.pdf", "nombre": nom_anexo})
            estado["anuncios"][reg] = {k: v for k, v in fila.items() if not k.startswith("_")} | {"anexos": ficheros}
            nuevos += 1
            guardar()
            if limite and nuevos >= limite:
                return list(estado["anuncios"].values())
        if (dt.date.today() - fin).days > 45:
            estado["ventanas"].append(clave)
        guardar()
    return list(estado["anuncios"].values())
