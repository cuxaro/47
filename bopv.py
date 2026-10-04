"""Prototipo: buscar en el BOP de Valencia y abrir cada anuncio en HTML (misma sesión JSF)."""
import http.cookiejar, pathlib, re, sys, time, urllib.parse, urllib.request, html, json
UA = "47-declaraciones/0.1 (+https://github.com/cuxaro/47; proyecto ciudadano de transparencia)"
OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
op.addheaders = [("User-Agent", UA), ("Accept-Language", "es,ca;q=0.8")]
r = op.open("https://bop.dival.es/bop/", timeout=90); page = r.read().decode("utf-8", "replace"); base = r.geturl()
m = re.search(r'<form id="([^"]+)"[^>]*action="([^"]+)"[^>]*>(?:(?!</form>).)*?name="buscador"(?:(?!</form>).)*?</form>', page, re.S)
form_id, action, form_html = m.group(1), html.unescape(m.group(2)), m.group(0)
campos = {}
for tag in re.findall(r'<(?:input|select|textarea)[^>]*>', form_html):
    n = re.search(r'name="([^"]+)"', tag); v = re.search(r'value="([^"]*)"', tag); t = re.search(r'type="([^"]+)"', tag)
    if n and (not t or t.group(1) not in ("submit", "checkbox", "button")):
        campos[n.group(1)] = html.unescape(v.group(1)) if v else ""
def ajax(d):
    req = urllib.request.Request(urllib.parse.urljoin(base, action), data=urllib.parse.urlencode(d).encode(),
                                 headers={"Faces-Request": "partial/ajax", "X-Requested-With": "XMLHttpRequest",
                                          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"})
    time.sleep(2)
    return op.open(req, timeout=120).read().decode("utf-8", "replace")
def vs_de(x): return re.search(r'ViewState:0"><!\[CDATA\[(.*?)\]\]>', x).group(1)
d = dict(campos)
d.update({"buscador": sys.argv[1], "filtroCalendarioIni_input": sys.argv[2], "filtroCalendarioFin_input": sys.argv[3],
          "javax.faces.partial.ajax": "true", "javax.faces.source": "buscarBtn", "javax.faces.partial.execute": "@all",
          "javax.faces.partial.render": "messages boletines3 edictos", "buscarBtn": "buscarBtn", form_id: form_id})
x = ajax(d); (OUT / "busqueda.xml").write_text(x); vs = vs_de(x)
total = re.search(r'rowCount:(\d+)', x); print("resultados", total and total.group(1), file=sys.stderr)
lista_form = re.search(r'PrimeFaces\.ab\(\{s:&quot;list:\d+:[^&]+&quot;,f:&quot;([^&]+)&quot;', x).group(1)
ids = re.findall(r'id="(list:(\d+):[^"]+)"[^>]*aria-label="Vore HTML"', x)
indice = []
for src, n in ids[: int(sys.argv[4])]:
    y = ajax({lista_form: lista_form, "javax.faces.ViewState": vs, "javax.faces.partial.ajax": "true",
              "javax.faces.source": src, "javax.faces.partial.execute": "@all", "javax.faces.partial.render": "dlgHTML", src: src})
    vs = vs_de(y)
    (OUT / f"anuncio_{n}.xml").write_text(y)
    print(n, len(y), "no trobat" in y, file=sys.stderr)
