import random

import pytest

from app.pdf_reader import PdfInvalido, read_pdf
from eval.generate_invoices import escanear


def test_pdf_digital_devuelve_texto(pdf_bytes):
    contenido = read_pdf(pdf_bytes)
    assert not contenido.escaneado
    assert "F2026-0001" in contenido.texto
    assert "B12345674" in contenido.texto
    assert contenido.paginas == 1


def test_pdf_escaneado_devuelve_imagenes(pdf_bytes):
    contenido = read_pdf(escanear(pdf_bytes, random.Random(1)))
    assert contenido.escaneado
    assert len(contenido.imagenes) == 1
    assert contenido.imagenes[0].startswith(b"\x89PNG")


def test_lee_desde_ruta(tmp_path, pdf_bytes):
    ruta = tmp_path / "f.pdf"
    ruta.write_bytes(pdf_bytes)
    assert "Licencia anual" in read_pdf(ruta).texto


def test_pdf_corrupto():
    with pytest.raises(PdfInvalido):
        read_pdf(b"%PDF-1.4 esto no es un pdf")
