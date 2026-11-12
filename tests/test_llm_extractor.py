from types import SimpleNamespace

import anthropic
import pytest

from app import llm_extractor
from app.llm_extractor import ExtractionError, build_content, estimate_cost_eur, extract
from app.pdf_reader import PdfContent


def respuesta(factura, stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=factura if stop_reason == "end_turn" else None,
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=300),
    )


class FakeMessages:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    def parse(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)


@pytest.fixture
def fake_client(monkeypatch):
    def instalar(*respuestas):
        messages = FakeMessages(respuestas)
        monkeypatch.setattr(llm_extractor, "get_client", lambda: SimpleNamespace(messages=messages))
        return messages

    return instalar


def test_extract_devuelve_factura_y_metricas(fake_client, factura):
    messages = fake_client(respuesta(factura))
    result = extract(PdfContent(texto="FACTURA ..."), model="claude-haiku-5-5")
    assert result.factura == factura
    assert (result.tokens_entrada, result.tokens_salida) == (1000, 300)
    assert result.coste_eur == estimate_cost_eur("claude-haiku-5-5", 1000, 300)
    assert messages.llamadas[0]["output_format"].__name__ == "Factura"


def test_extract_reintenta_respuesta_incompleta(fake_client, factura):
    messages = fake_client(respuesta(None, "max_tokens"), respuesta(factura))
    result = extract(PdfContent(texto="FACTURA ..."), model="claude-haiku-5-5")
    assert result.factura == factura
    assert result.tokens_entrada == 2000  # se suman los tokens de los dos intentos
    assert len(messages.llamadas) == 2


def test_extract_falla_tras_reintentos(fake_client):
    fake_client(*[respuesta(None, "refusal")] * 3)
    with pytest.raises(ExtractionError):
        extract(PdfContent(texto="FACTURA ..."))


def test_extract_sin_credenciales_da_error_controlado(monkeypatch):
    class SinCredenciales:
        def parse(self, **kwargs):
            raise anthropic.AnthropicError("Credentials file not found")

    monkeypatch.setattr(llm_extractor, "get_client",
                        lambda: SimpleNamespace(messages=SinCredenciales()))
    with pytest.raises(ExtractionError, match="no configurada"):
        extract(PdfContent(texto="FACTURA ..."))


def test_api_devuelve_502_si_falla_el_llm(client, pdf_bytes, monkeypatch):
    from app import main

    def falla(*args, **kwargs):
        raise ExtractionError("API del LLM no configurada")

    monkeypatch.setattr(main, "extract", falla)
    r = client.post("/facturas", files={"archivo": ("f.pdf", pdf_bytes, "application/pdf")})
    assert r.status_code == 502
    assert "no configurada" in r.json()["detail"]


def test_build_content_texto_e_imagen():
    texto = build_content(PdfContent(texto="hola"))
    assert texto[0]["type"] == "text" and "hola" in texto[0]["text"]

    imagen = build_content(PdfContent(texto="", imagenes=[b"\x89PNGdata"]))
    assert imagen[0]["type"] == "image"
    assert imagen[0]["source"]["media_type"] == "image/png"
    assert imagen[-1]["type"] == "text"


def test_coste():
    assert estimate_cost_eur("modelo-desconocido", 10_000, 10_000) == 0
    assert estimate_cost_eur("claude-sonnet-5-5", 1_000_000, 0) > 1
