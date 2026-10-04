"""Descargas educadas: una petición cada pocos segundos, con caché en disco.

No hace falta ninguna clave ni credencial: todo lo que se descarga son
páginas y documentos públicos.
"""
from __future__ import annotations

import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

AGENTE = "47-declaraciones/0.1 (+https://github.com/cuxaro/47; proyecto ciudadano de transparencia)"
PAUSA = 2.0          # segundos entre peticiones al mismo servidor
REINTENTOS = 3
_ultima = 0.0


def descargar(url: str, destino: str | pathlib.Path, datos: dict | None = None,
              refrescar: bool = False) -> pathlib.Path | None:
    """Descarga `url` en `destino` (si no está ya). Devuelve la ruta o None si no existe (404)."""
    global _ultima
    destino = pathlib.Path(destino)
    if destino.exists() and destino.stat().st_size > 0 and not refrescar:
        return destino
    destino.parent.mkdir(parents=True, exist_ok=True)
    cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
    for intento in range(1, REINTENTOS + 1):
        espera = PAUSA - (time.time() - _ultima)
        if espera > 0:
            time.sleep(espera)
        _ultima = time.time()
        try:
            req = urllib.request.Request(url, data=cuerpo, headers={
                "User-Agent": AGENTE, "Accept-Language": "es,ca;q=0.8"})
            with urllib.request.urlopen(req, timeout=120) as r:
                contenido = r.read()
            tmp = destino.with_suffix(destino.suffix + ".tmp")
            tmp.write_bytes(contenido)
            tmp.replace(destino)
            return destino
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                print(f"  [{e.code}] {url}", file=sys.stderr)
                return None
            print(f"  error {e.code} en {url} (intento {intento})", file=sys.stderr)
        except Exception as e:  # red caída, tiempo agotado…
            print(f"  fallo en {url}: {e!r} (intento {intento})", file=sys.stderr)
        time.sleep(5 * intento)
    return None
