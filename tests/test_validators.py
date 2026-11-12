from datetime import date

import pytest

from app.schemas import Factura, Severidad
from app.validators import validar_cif, validar_dni_nie, validar_factura, validar_nif

HOY = date(2026, 11, 11)


@pytest.mark.parametrize("doc", ["12345678Z", "12345678-z", "X1234567L", "Y1234567X", "00000000T"])
def test_dni_nie_validos(doc):
    assert validar_dni_nie(doc)


@pytest.mark.parametrize("doc", ["12345678A", "1234567Z", "X1234567A", "ABCDEFGHZ", ""])
def test_dni_nie_invalidos(doc):
    assert not validar_dni_nie(doc)


@pytest.mark.parametrize("cif", ["B12345674", "A58818501", "Q2826000H", "P0800000B", "ESB12345674"])
def test_cif_validos(cif):
    assert validar_cif(cif)


@pytest.mark.parametrize("cif", ["B12345675", "I12345674", "B1234567", "B12A45674"])
def test_cif_invalidos(cif):
    assert not validar_cif(cif)


def test_validar_nif_acepta_los_tres_tipos():
    assert validar_nif("B12345674") and validar_nif("12345678Z") and validar_nif("X1234567L")


def test_factura_correcta_sin_avisos(factura):
    assert validar_factura(factura, hoy=HOY) == []


def test_factura_sin_irpf(datos):
    datos.update(retencion_irpf=None, total=907.5)
    assert validar_factura(Factura.model_validate(datos), hoy=HOY) == []


def campos(datos) -> set[str]:
    return {a.campo for a in validar_factura(Factura.model_validate(datos), hoy=HOY)}


def test_nif_invalido(datos):
    datos["emisor"]["nif"] = "B12345675"
    datos["receptor"]["nif"] = "12345678A"
    assert campos(datos) == {"emisor.nif", "receptor.nif"}


def test_lineas_no_suman_base(datos):
    datos["lineas"][1]["importe"] = 260.0
    datos["lineas"][1]["precio_unitario"] = 260.0
    assert campos(datos) == {"base_imponible"}


def test_importe_de_linea_incoherente(datos):
    datos["lineas"][0]["precio_unitario"] = 55.0
    assert campos(datos) == {"lineas[0].importe"}


def test_tolerancia_de_dos_centimos(datos):
    datos["base_imponible"] = 750.02
    datos["cuota_iva"] = 157.5
    datos["total"] = 795.01
    assert campos(datos) == set()


def test_cuota_iva_erronea(datos):
    datos["cuota_iva"] = 150.0
    datos["total"] = 787.5
    assert campos(datos) == {"cuota_iva"}


def test_total_erroneo(datos):
    datos["total"] = 805.0
    assert campos(datos) == {"total"}


def test_tipo_iva_no_habitual(datos):
    datos.update(tipo_iva=7.0, cuota_iva=52.5, total=690.0)
    assert campos(datos) == {"tipo_iva"}


def test_fecha_futura(datos):
    datos["fecha_emision"] = "2027-01-01"
    avisos = validar_factura(Factura.model_validate(datos), hoy=HOY)
    assert [a.campo for a in avisos] == ["fecha_emision"]
    assert avisos[0].severidad == Severidad.error


def test_sin_lineas(datos):
    datos["lineas"] = []
    assert campos(datos) == {"lineas"}
