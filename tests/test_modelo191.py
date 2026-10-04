"""Pruebas del lector del «modelo de totales» (diputaciones y ayuntamientos)."""
from extractor import modelo191
from extractor.locales import _cargo, _entidad, personas

FICHA = """
ANUNCIO
TITULAR DEL CÀRREC / TITULAR DEL CARGO
NOM / NOMBRE     PRIMER COGNOM / PRIMER APELLIDO SEGON COGNOM / SEGUNDO APELLIDO
     María José                 Ferrer                     San Segundo

CÀRREC ORIGEN DE LA DECLARACIÓ / CARGO ORIGEN DE LA DECLARACIÓN
TIPUS DE CÀRREC / TIPO DE CARGO DENOMINACIÓ / DENOMINACIÓN
Concejala                       Primera Teniente de Alcalde
TIPUS DE DECLARACIÓ / TIPO DE DECLARACIÓ
    INICIAL            FINAL         x MODIFICACIÓ / MODIFICACIÓN

I. ACTIU / ACTIVO                                                  VALOR (en euros)
  1. Béns immobles (segons valor cadastral i percentatge de titularitat)      143.294,01
  2. Valor total d'altres béns (segons percentatge de titularitat)            108.274,21
  3. Total                                                                    251.568,22
II. PASSIU / PASIVO
  Crèdits, préstecs, deutes                                                    30.000,00
III. ACTIVITATS / ACTIVIDADES
  Abogada
"""

TABLA = """
Nom i Cognoms          Càrrec públic origen de        Béns        Valor total     Total Actiu     Crèdits
Lara Romero Giner      Alcaldessa presidenta       66.055,22€        4.515€       70.570,22€      71.498,60€    - Alcaldessa
                       (Grup Socialista)                                                                         - Professora de Secundària
Amparo Inés Bo         Regidora Grup Socialista   143.061,68€       1.530,9€     144.592,58€     219.805,53€    - Regidora
Chover                                                                                                           - Funcionària
"""


def test_ficha_bilingue():
    (f,) = modelo191.leer(FICHA)
    assert f["nombre_completo"] == "María José Ferrer San Segundo"   # «Segundo» no es un rótulo
    assert (f["inmuebles"], f["otros_bienes"], f["total_activo"]) == (143294.01, 108274.21, 251568.22)
    assert f["pasivo"] == 30000.0
    assert f["suma_cuadra"] is True
    assert f["tipo_marcado"] == "modificacion"
    assert modelo191.partir_nombre(f["nombre_completo"]) == ("María José", "Ferrer San Segundo")


def test_tabla_con_nombres_en_dos_lineas():
    a, b = modelo191.leer(TABLA)
    assert a["nombre_completo"] == "Lara Romero Giner"
    assert a["cargo"] == "Alcaldessa presidenta (Grup Socialista)"
    assert a["pasivo"] == 71498.60
    assert "Professora" in a["actividades"]
    assert b["nombre_completo"] == "Amparo Inés Bo Chover"
    assert b["total_activo"] == 144592.58


def test_cargo_y_entidad():
    assert _cargo("Directivo Director General de Movilidad") == ("Director General de Movilidad", "directivo")
    assert _cargo("Concejal a Concejal 2023 2027") == ("Concejal 2023 2027", "electo")
    assert _cargo("")[1] == "electo"
    assert _entidad("Ajuntament d'Ayora")[0] == "Ayuntamiento de Ayora"
    assert _entidad("Diputació Provincial de València / Secretaria General") is None


def _f(tipo, fecha, total):
    return {"nombre_completo": "Ana Pérez Gil", "nombre": "Ana", "apellidos": "Pérez Gil", "cargo": "Concejala",
            "clase_cargo": "electo", "institucion": "Ayuntamiento de X", "tipo_institucion": "Ayuntamiento",
            "provincia": "Valencia", "tipo": tipo, "fecha": fecha, "metodo": "texto", "inmuebles": total,
            "otros_bienes": 0.0, "total_activo": total, "pasivo": None, "suma_cuadra": True}


def test_cese_del_mandato_anterior_no_da_de_baja():
    # toma de posesión en julio de 2023 y, después, se publica el cese del mandato 2019-2023
    (p,) = personas([_f("inicial", "2023-07-10", 100.0), _f("final", "2023-09-20", 90.0)])
    assert p["en_activo"] is True and p["valor_catastral"] == 100.0
    # un cese publicado en 2025 sí es una baja
    (p,) = personas([_f("inicial", "2023-07-10", 100.0), _f("final", "2025-02-01", 90.0)])
    assert p["en_activo"] is False
