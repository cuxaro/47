"""Prueba del buscador del BOP de Valencia (aplicación JSF/PrimeFaces)."""
import http.cookiejar, pathlib, re, sys, time, urllib.parse, urllib.request, html
UA = "47-declaraciones/0.1 (+https://github.com/cuxaro/47; proyecto ciudadano de transparencia)"
OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
op.addheaders = [("User-Agent", UA), ("Accept-Language", "es,ca;q=0.8")]
r = op.open("https://bop.dival.es/bop/", timeout=90); page = r.read().decode("utf-8", "replace"); base = r.geturl()
print("base", base, len(page), file=sys.stderr)
m = re.search(r'<form id="([^"]+)"[^>]*action="([^"]+)"[^>]*>(?:(?!</form>).)*?name="buscador"(?:(?!</form>).)*?</form>', page, re.S)
form_id, action, form_html = m.group(1), html.unescape(m.group(2)), m.group(0)
campos = {}
for tag in re.findall(r'<(?:input|select|textarea)[^>]*>', form_html):
    n = re.search(r'name="([^"]+)"', tag); v = re.search(r'value="([^"]*)"', tag); t = re.search(r'type="([^"]+)"', tag)
    if n and (not t or t.group(1) not in ("submit", "checkbox", "button")):
        campos[n.group(1)] = html.unescape(v.group(1)) if v else ""
print(form_id, action, campos, file=sys.stderr)
def buscar(texto, ini, fin, nombre):
    d = dict(campos)
    d.update({"buscador": texto, "filtroCalendarioIni_input": ini, "filtroCalendarioFin_input": fin,
              "javax.faces.partial.ajax": "true", "javax.faces.source": "buscarBtn",
              "javax.faces.partial.execute": "@all", "javax.faces.partial.render": "messages boletines3 edictos",
              "buscarBtn": "buscarBtn", form_id: form_id})
    req = urllib.request.Request(urllib.parse.urljoin(base, action), data=urllib.parse.urlencode(d).encode(),
                                 headers={"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest",
                                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    try:
        x = op.open(req, timeout=120).read()
    except Exception as e:
        x = repr(e).encode()
    (OUT / nombre).write_bytes(x); print(nombre, len(x), file=sys.stderr); time.sleep(3)
buscar("declaraciones bienes actividades", "01/09/2023", "31/10/2023", "bopv_es.xml")
buscar("declaracions bens activitats", "01/09/2023", "31/10/2023", "bopv_va.xml")
buscar('"titular del cargo"', "01/06/2023", "31/12/2023", "bopv_titular.xml")
