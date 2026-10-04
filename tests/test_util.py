from extractor.util import a_numero, a_porcentaje, a_provincia, parecido


def test_importes():
    casos = {
        "35 807,98€": 35807.98, "1747.05 €": 1747.05, "45.000": 45000.0, "1.000.000": 1000000.0,
        "-3787,09": -3787.09, "3600 €": 3600.0, "30057,72": 30057.72, "2 344,91€": 2344.91,
        "83.503,34 7": 83503.34, "45798'50": 45798.5, "70,972,93": 70972.93, "13681.81": 13681.81,
        "8.552 €": 8552.0, "1,4": 1.4, "4:622,51": 4622.51,
    }
    for txt, esperado in casos.items():
        assert a_numero(txt) == esperado, txt
    assert a_numero("") is None
    assert a_numero("sin datos") is None


def test_porcentajes():
    assert a_porcentaje("50%") == 50.0
    assert a_porcentaje("1/2") == 50.0
    assert a_porcentaje("33,33 %") == 33.33
    assert a_porcentaje("P") is None


def test_provincias():
    assert a_provincia("CASTELLÓN") == "Castellón"
    assert a_provincia("Alacant") == "Alicante"
    assert a_provincia("VALÈNCIA") == "Valencia"
    assert a_provincia("ELCHE (ALICANTE)") == "Alicante"
    assert a_provincia("VALENCLA") == "Valencia"      # errata típica del OCR
    assert a_provincia("xx") is None


def test_parecido():
    assert parecido("ABADSOLER", "Abad Soler") == 1.0
    assert parecido("FERNÁNDEZ APARICIO", "Fernandez Aparicio") == 1.0
