"""Sonda de reconocimiento (rama temporal): descarga unas pocas URL públicas para estudiar su estructura."""
import hashlib, json, pathlib, sys, time, urllib.request, urllib.error, urllib.parse
UA = "47-declaraciones/0.1 (+https://github.com/cuxaro/47; proyecto ciudadano de transparencia)"
OUT = pathlib.Path("out"); OUT.mkdir(exist_ok=True)
index = []
for line in pathlib.Path("urls.txt").read_text().splitlines():
    url = line.strip()
    if not url or url.startswith("#"): continue
    data = None
    if url.startswith("POST "):
        _, url, body = (url.split(" ", 2) + [""])[:3]; data = body.encode()
    h = hashlib.sha1((url + (data or b"").decode()).encode()).hexdigest()[:10]
    rec = {"url": url, "id": h, "post": (data or b"").decode()}
    try:
        u = urllib.parse.urlsplit(url)
        url_q = urllib.parse.urlunsplit((u.scheme, u.netloc, urllib.parse.quote(u.path, safe="/%"), u.query, ""))
        req = urllib.request.Request(url_q, data=data, headers={"User-Agent": UA, "Accept-Language": "es,ca;q=0.8"})
        with urllib.request.urlopen(req, timeout=90) as r:
            body = r.read(); ctype = r.headers.get("Content-Type", "")
            ext = ".pdf" if body[:4] == b"%PDF" else (".json" if "json" in ctype else (".csv" if "csv" in ctype else (".xml" if "xml" in ctype else ".html")))
            (OUT / (h + ext)).write_bytes(body)
            rec.update(status=r.status, ctype=ctype, bytes=len(body), final=r.geturl(), file=h + ext)
    except urllib.error.HTTPError as e:
        rec.update(status=e.code, error=str(e))
    except Exception as e:
        rec.update(status=None, error=repr(e))
    index.append(rec); print(rec, file=sys.stderr); time.sleep(2)
(OUT / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
