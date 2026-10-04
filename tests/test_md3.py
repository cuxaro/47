"""Prueba del lector del formulario MD3 con una página inventada (sin PDF ni OCR)."""
from extractor.md3 import leer_boletin


def _linea(y, x, texto):
    palabras, cx = [], x
    for t in texto.split():
        palabras.append({"t": t, "x0": cx, "x1": cx + 5 * len(t), "y0": y, "y1": y + 6, "v": 0})
        cx += 5 * len(t) + 3
    return palabras


def _fila(y, *celdas):
    return [{"x0": x0, "y0": y, "x1": x1, "y1": y + 9, "t": t} for x0, x1, t in celdas]


def _pagina():
    palabras, casillas = [], []
    for y, x, t in [
        (130, 440, "REGISTRE ENTRADA 21/06/2023 13:43 X071691"),
        (236, 258, "REGISTRO DE ACTIVIDADES, BIENES E INTERESES"),
        (312, 150, "NOM ALICIA COGNOMS ANDUJAR DURA"),
        (324, 150, "CIRCUMSCRIPCIÓ ELECTORAL VALENCIA"),
        (335, 150, "PARTIT, FEDERACIÓ AMB QUÈ CONCORRE A LES ELECCIONS PSPV-PSOE"),
        (392, 148, "DECLARACIONES DE ACTIVIDADES Y DE BIENES E INTERESES"),
        (434, 150, "1.- BIENES INMUEBLES URBANOS Y RÚSTICOS"),
        (457, 150, "Clave (*) Tipo(**) Situación (provincia) Valor catastral"),
        (488, 150, "Valor catastral del conjunto (I)"),
        (551, 150, "2.- BIENES Y DERECHOS DE NATURALEZA NO INMOBILIARIA"),
        (566, 150, "Descripción Valor (euros)"),
        (631, 150, "Valor global conjunto"),
        (659, 150, "3.- PASIVO"),
        (674, 150, "Descripción Valor (euros)"),
        (713, 150, "Valor global conjunto"),
        (740, 148, "(I) Estos datos se deberán cumplimentar con carácter obligatorio"),
    ]:
        palabras += _linea(y, x, t)
    casillas += _fila(471, (148, 211, "Pleno dominio"), (211, 267, "Vivienda"), (267, 323, "100"),
                      (323, 382, "VALENCIA"), (382, 464, "30057,72"))
    casillas += _fila(484, (211, 464, "30057,72"))
    casillas += _fila(575, (148, 351, "CUENTA BANCARIA"), (351, 464, "1747.05 €"))
    casillas += _fila(584, (148, 351, "VOLVO S60"), (351, 464, "30.000"))
    casillas += _fila(627, (207, 464, "31.747,05"))
    casillas += _fila(683, (148, 384, "PRESTAMO HIPOTECARIO"), (384, 464, "20474.41 €"))
    casillas += _fila(709, (207, 464, "20474,41"))
    return {"num": 7, "ancho": 595, "alto": 842, "metodo": "texto",
            "palabras": palabras, "sello": palabras, "casillas": casillas}


def test_declaracion_completa():
    (d,) = leer_boletin([_pagina()])
    assert d["sello"] == "X071691" and d["fecha_registro"] == "2023-06-21"
    assert d["persona"]["nombre"] == "ALICIA" and d["persona"]["apellidos"] == "ANDUJAR DURA"
    assert d["persona"]["circunscripcion"] == "Valencia"
    (inm,) = d["inmuebles"]
    assert (inm["clave"], inm["tipo"], inm["porcentaje"], inm["provincia"], inm["valor_catastral"]) == \
        ("P", "V", 100.0, "Valencia", 30057.72)
    assert d["total_catastral"] == 30057.72 and d["suma_inmuebles_cuadra"] is True
    assert [(i["categoria"], i["valor"]) for i in d["otros_bienes"]] == [("cuentas", 1747.05), ("vehiculos", 30000.0)]
    assert d["total_otros_bienes"] == 31747.05 and d["suma_otros_cuadra"] is True
    assert [(i["categoria"], i["valor"]) for i in d["pasivo"]] == [("hipoteca", 20474.41)]
    assert d["total_pasivo"] == 20474.41
    assert d["avisos"] == [] and d["ilegible"] is False
