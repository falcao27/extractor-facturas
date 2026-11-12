# 🧾 Extractor de facturas con IA

[![CI](https://github.com/falcao27/-extractor-facturas/actions/workflows/ci.yml/badge.svg)](https://github.com/falcao27/-extractor-facturas/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Servicio que recibe el PDF de una factura española, extrae los datos con un LLM (Claude),
**valida NIF/CIF, IVA, IRPF y totales** con reglas de negocio y lo exporta todo a Excel.

**Demo:** _[enlace de Render]_ · **API:** `/docs` (Swagger automático)

<!-- ![Demo](docs/demo.gif) -->

## El problema

Las pymes y gestorías españolas reciben cientos de facturas en PDF con formatos distintos y
las teclean a mano en su software contable. Un LLM puede leerlas, pero **se equivoca**: este
proyecto no se fía del modelo, sino que comprueba cada resultado con las reglas fiscales
y **mide la precisión** sobre un conjunto de prueba.

## Qué extrae

Número, fecha de emisión, emisor y receptor (razón social + NIF/CIF), líneas (descripción,
cantidad, precio unitario, importe), base imponible, tipo de IVA (21/10/4/0 %), cuota de IVA,
retención de IRPF y total.

## Reglas de validación

Cada regla genera un **aviso** (no bloquea): el usuario revisa y corrige.

| Regla | Detalle |
|---|---|
| NIF / NIE | 8 dígitos módulo 23 → letra de control (NIE: X/Y/Z → 0/1/2) |
| CIF | letra inicial + 7 dígitos + dígito o letra de control |
| Líneas | Σ importes = base imponible; cantidad × precio = importe |
| IVA | base × tipo / 100 = cuota; tipo ∈ {21, 10, 4, 0} |
| Total | base + IVA − IRPF = total |
| Fecha | la emisión no puede estar en el futuro |

Las cuentas usan `Decimal` con tolerancia de 0,02 €.

## Evaluación

`eval/generate_invoices.py` genera 30 facturas ficticias con Faker (`es_ES`) y reportlab, cada
una con su JSON de referencia: **3 diseños** (uno con formato español `1.234,56`), con y sin
IRPF, de 1 a 10 líneas, **4 escaneadas** (página rasterizada y girada, sin capa de texto, que
se envía como imagen al modelo) y **3 trampas** (NIF inválido o total erróneo).

`eval/run_eval.py` compara campo a campo (texto normalizado, números con tolerancia de 0,01)
y guarda la caché de respuestas para no pagar dos veces la misma factura.

```bash
python -m eval.run_eval --models claude-haiku-5-5 claude-sonnet-5-5
```

<!-- RESULTADOS: sustituir por el contenido de eval/results.md -->
| Campo | claude-haiku-5-5 | claude-sonnet-5-5 |
|---|---:|---:|
| NIF emisor | _pendiente_ | _pendiente_ |
| Base imponible | _pendiente_ | _pendiente_ |
| Total | _pendiente_ | _pendiente_ |
| Coste medio por factura | _pendiente_ | _pendiente_ |

## Arquitectura

```
PDF ─► FastAPI (valida: solo PDF, ≤ 5 MB, límite por IP)
        │
        ├─► pdfplumber ── texto ──────────┐
        │     └─ < 50 caracteres → PNG ───┤
        │                                 ▼
        │                 Claude · salida estructurada (esquema Pydantic)
        │                                 │
        ├─► reglas de negocio (NIF, IVA, IRPF, totales, fecha) → avisos
        ├─► PostgreSQL (datos, avisos JSONB, modelo, tokens, coste, tiempo)
        └─► Excel (pandas + openpyxl)          Streamlit ◄─ revisión y corrección
```

| Capa | Herramienta |
|---|---|
| API | FastAPI + Uvicorn |
| Esquema | Pydantic v2 (el mismo modelo para el LLM, la API y la evaluación) |
| LLM | API de Anthropic, `messages.parse` con salida estructurada |
| PDF | pdfplumber (texto) y renderizado a PNG para escaneados |
| Base de datos | PostgreSQL + SQLAlchemy 2 + Alembic |
| Interfaz | Streamlit |
| Calidad | Pytest (cobertura > 90 %), Ruff, GitHub Actions, logs JSON |
| Infra | Docker Compose, Render |

**Decisiones:**

- **Salida estructurada** en lugar de pedir JSON en el prompt: el servidor garantiza que la
  respuesta cumple el esquema, y Pydantic la valida otra vez. Los reintentos solo cubren
  `refusal`/`max_tokens`; el SDK ya reintenta timeouts, 429 y 5xx.
- **`float` en el esquema del LLM y `Decimal` en las cuentas**, para no depender de cómo cada
  proveedor serializa decimales.
- **Los PDF no se guardan**: se procesan en memoria y solo se persisten los datos extraídos (RGPD).

## API

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/facturas` | Sube un PDF: extrae, valida, guarda y devuelve el JSON con avisos |
| GET | `/facturas` | Lista paginada, filtros por emisor (nombre o NIF) y periodo |
| GET | `/facturas/{id}` | Detalle |
| PATCH | `/facturas/{id}` | Corrección manual (revalida); `confirmar: true` → `revisada` |
| GET | `/facturas/export.xlsx` | Excel con hoja de facturas y hoja de líneas |
| GET | `/health` | Estado de la API y de la base de datos |

Estados: `procesada`, `con_avisos`, `revisada`, `error`.

## Cómo ejecutarlo

### Docker (recomendado)

```bash
cp .env.example .env      # rellena ANTHROPIC_API_KEY
docker compose up --build
```

- Interfaz: http://localhost:8501
- API y documentación: http://localhost:8000/docs

### Local

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate                # Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
copy .env.example .env                # rellena ANTHROPIC_API_KEY y DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload
streamlit run ui/streamlit_app.py     # en otra terminal
```

### Modo demo (sin clave ni créditos)

Con `LLM_PROVIDER=demo` no se llama al LLM: la API reconoce las 30 facturas de
`eval/dataset` por su hash y devuelve los datos de referencia. Todo lo demás es real:
lectura del PDF, validaciones, avisos, base de datos, corrección y Excel.

```powershell
$env:LLM_PROVIDER="demo"; $env:DATABASE_URL="sqlite:///local.db"
alembic upgrade head
uvicorn app.main:app                  # y en otra terminal: streamlit run ui/streamlit_app.py
```

Prueba con `factura_010.pdf` (total erróneo) o `factura_007.pdf` (NIF inválido) para ver
los avisos.

### Tests y calidad

```bash
ruff check .
pytest --cov                          # el LLM se simula: los tests no gastan créditos
python -m eval.generate_invoices      # regenera el dataset (determinista, seed 42)
```

## Despliegue en Render

`render.yaml` define la API, la interfaz y PostgreSQL. En Render: **New → Blueprint →** este
repositorio. Después, rellena `ANTHROPIC_API_KEY` en la API y `API_URL` en la interfaz.

> La capa gratuita de Render duerme tras 15 minutos sin uso: la primera petición puede tardar
> ~1 minuto. La demo limita a 20 facturas por IP y día para proteger los créditos.

## Privacidad

Todas las facturas del repositorio son **ficticias**, generadas con Faker. Los PDF subidos se
procesan en memoria y **nunca se guardan**; solo se almacenan los datos extraídos. No subas
facturas reales a la demo pública.

## Próximos pasos

- Cola de trabajo (Celery/RQ) y Batch API para procesar miles de facturas al día
- Caché por hash del PDF para no reprocesar duplicados
- Autenticación y multiusuario
- Exportación a formatos contables (A3, Contaplus) y Facturae/VeriFactu

## Licencia

MIT © Jefferson Falcão
