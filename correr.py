import datetime as dt, pathlib, sys
from extractor import bopv
ind = bopv.recoger(pathlib.Path("bopv"), dt.date(2023, 6, 1))
print("anuncios", len(ind), file=sys.stderr)
