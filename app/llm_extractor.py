"""Extracción con Claude usando salida estructurada (JSON garantizado con el esquema Factura)."""

import base64
import logging
import time
from dataclasses import dataclass

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.pdf_reader import PdfContent
from app.schemas import Factura

logger = logging.getLogger(__name__)

SYSTEM = (
    "Eres un experto en contabilidad española. Extrae los datos de la factura exactamente "
    "como aparecen; no corrijas ni recalcules importes aunque parezcan erróneos. "
    "No inventes valores. "
    "Los importes en formato español usan punto para miles y coma para decimales "
    "(1.234,56 significa 1234.56): devuélvelos siempre como número con punto decimal. "
    "Las fechas DD/MM/AAAA son día/mes/año. "
    "La retención de IRPF se devuelve como importe positivo, o null si no hay."
)

# USD por millón de tokens (entrada, salida). Precios de lista de la API de Anthropic.
PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}

MAX_RETRIES = 2


class ExtractionError(RuntimeError):
    pass


@dataclass
class ExtractionResult:
    factura: Factura
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    coste_eur: float
    tiempo_ms: int


def estimate_cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES_USD_PER_MTOK.get(model, (0.0, 0.0))
    usd = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return round(usd * settings.usd_to_eur, 6)


def build_content(pdf: PdfContent) -> list[dict]:
    if not pdf.escaneado:
        return [{"type": "text", "text": f"Texto de la factura:\n\n{pdf.texto}"}]
    blocks: list[dict] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(img).decode("ascii"),
            },
        }
        for img in pdf.imagenes
    ]
    blocks.append({"type": "text", "text": "Extrae los datos de esta factura escaneada."})
    return blocks


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # El SDK ya reintenta 2 veces timeouts, 429 y 5xx con backoff exponencial.
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key or None,
            timeout=settings.llm_timeout_s,
            max_retries=MAX_RETRIES,
        )
    return _client


def extract(pdf: PdfContent, model: str | None = None) -> ExtractionResult:
    model = model or settings.llm_model
    client = get_client()
    content = build_content(pdf)
    tokens_in = tokens_out = 0
    start = time.perf_counter()
    last_error: Exception | None = None

    # Reintento propio solo para respuestas que no validan (p. ej. refusal o max_tokens).
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.parse(
                model=model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": content}],
                output_format=Factura,
            )
        except anthropic.APIStatusError as exc:
            raise ExtractionError(f"Error de la API del LLM ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("No se pudo conectar con la API del LLM") from exc
        except ValidationError as exc:
            last_error = exc
            logger.warning("respuesta inválida del LLM", extra={"intento": attempt + 1})
            continue

        tokens_in += response.usage.input_tokens
        tokens_out += response.usage.output_tokens
        if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
            last_error = ExtractionError(f"Respuesta incompleta: {response.stop_reason}")
            continue

        return ExtractionResult(
            factura=response.parsed_output,
            modelo=model,
            tokens_entrada=tokens_in,
            tokens_salida=tokens_out,
            coste_eur=estimate_cost_eur(model, tokens_in, tokens_out),
            tiempo_ms=int((time.perf_counter() - start) * 1000),
        )

    raise ExtractionError("El LLM no devolvió una factura válida") from last_error
