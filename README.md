# Extractor de facturas con IA

Servicio que recibe el PDF de una factura española, extrae los datos con un LLM (Claude),
valida NIF/CIF e importes y los exporta a Excel.

> En construcción. Las facturas del repositorio son ficticias; los PDF subidos se borran
> después de procesarlos.

## Desarrollo local

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env          # y rellena ANTHROPIC_API_KEY
uvicorn app.main:app --reload   # documentación en http://localhost:8000/docs
```

Calidad:

```bash
ruff check .
pytest
```

## Licencia

MIT
