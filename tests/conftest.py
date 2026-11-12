import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import main
from app.database import Base, get_db
from app.llm_extractor import ExtractionResult
from app.schemas import Factura
from eval.generate_invoices import dibujar

DATASET = Path(__file__).resolve().parents[1] / "eval" / "dataset"

DATOS = {
    "numero": "F2026-0001",
    "fecha_emision": "2026-03-15",
    "emisor": {"nombre": "Consultora Ejemplo S.L.", "nif": "B12345674"},
    "receptor": {"nombre": "Ana García López", "nif": "12345678Z"},
    "lineas": [
        {"descripcion": "Horas de consultoría", "cantidad": 10, "precio_unitario": 50.0,
         "importe": 500.0},
        {"descripcion": "Licencia anual", "cantidad": 1, "precio_unitario": 250.0,
         "importe": 250.0},
    ],
    "base_imponible": 750.0,
    "tipo_iva": 21.0,
    "cuota_iva": 157.5,
    "retencion_irpf": 112.5,
    "total": 795.0,
}


@pytest.fixture
def datos() -> dict:
    return json.loads(json.dumps(DATOS))


@pytest.fixture
def factura(datos) -> Factura:
    return Factura.model_validate(datos)


@pytest.fixture
def pdf_bytes(datos) -> bytes:
    return dibujar(datos, layout=0, direcciones=("Calle Mayor 1, Madrid", "Calle Sol 2, Sevilla"))


@pytest.fixture
def client(monkeypatch, factura):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with testing_session() as db:
            yield db

    calls = []

    def fake_extract(contenido, model=None):
        calls.append(contenido)
        return ExtractionResult(
            factura=factura, modelo="claude-haiku-5-5", tokens_entrada=1200,
            tokens_salida=400, coste_eur=0.0003, tiempo_ms=850,
        )

    monkeypatch.setattr(main, "extract", fake_extract)
    main.app.dependency_overrides[get_db] = override_db
    main.rate_limiter.reset()
    with TestClient(main.app) as c:
        c.extract_calls = calls
        yield c
    main.app.dependency_overrides.clear()
