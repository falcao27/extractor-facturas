import logging
import time
import uuid
from collections import defaultdict
from datetime import date
from threading import Lock
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import repository
from app.config import settings
from app.database import get_db
from app.export import to_xlsx
from app.llm_extractor import ExtractionError, extract
from app.logging_config import request_id_var, setup_logging
from app.pdf_reader import PdfInvalido, read_pdf
from app.schemas import Factura, FacturaList, FacturaPatch, FacturaRead
from app.validators import validar_factura

setup_logging(settings.log_level)
logger = logging.getLogger("app")

app = FastAPI(
    title="Extractor de facturas con IA",
    version="1.0.0",
    description=(
        "Extrae y valida datos de facturas españolas en PDF (NIF/CIF, IVA, IRPF, totales) "
        "con un LLM y los exporta a Excel. Los PDF no se guardan: se procesan en memoria."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DbSession = Annotated[Session, Depends(get_db)]


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(rid)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    elapsed = int((time.perf_counter() - start) * 1000)
    response.headers["x-request-id"] = rid
    logger.info(
        "request",
        extra={
            "request_id": rid,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "ms": elapsed,
        },
    )
    return response


class RateLimiter:
    """Límite diario por IP en memoria; suficiente para una única instancia de demo."""

    def __init__(self, limit: int):
        self.limit = limit
        self._counts: dict[tuple[str, date], int] = defaultdict(int)
        self._lock = Lock()

    def check(self, ip: str) -> None:
        key = (ip, date.today())
        with self._lock:
            if self._counts[key] >= self.limit:
                raise HTTPException(
                    429, f"Límite de {self.limit} facturas por día alcanzado. Vuelve mañana."
                )
            self._counts[key] += 1

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


rate_limiter = RateLimiter(settings.rate_limit_per_day)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


async def leer_pdf_subido(archivo: UploadFile) -> bytes:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    nombre = archivo.filename or ""
    if not nombre.lower().endswith(".pdf") and archivo.content_type != "application/pdf":
        raise HTTPException(422, "Solo se aceptan archivos PDF")
    data = await archivo.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(422, f"El archivo supera el máximo de {settings.max_upload_mb} MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(422, "El archivo no es un PDF válido")
    return data


@app.get("/health", tags=["sistema"])
def health(db: DbSession) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        logger.exception("health: base de datos no disponible")
        database = "error"
    return {"status": "ok" if database == "ok" else "degraded", "database": database}


@app.post("/facturas", response_model=FacturaRead, status_code=201, tags=["facturas"])
async def subir_factura(
    request: Request, db: DbSession, archivo: Annotated[UploadFile, File()]
) -> FacturaRead:
    data = await leer_pdf_subido(archivo)
    rate_limiter.check(client_ip(request))

    try:
        contenido = await run_in_threadpool(read_pdf, data)
    except PdfInvalido as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        del data  # el PDF nunca se escribe en disco; solo se guardan los datos extraídos

    try:
        result = await run_in_threadpool(extract, contenido)
    except ExtractionError as exc:
        logger.error("extracción fallida", extra={"archivo": archivo.filename, "error": str(exc)})
        raise HTTPException(502, f"No se pudo extraer la factura: {exc}") from exc

    avisos = validar_factura(result.factura)
    row = repository.crear(db, archivo.filename or "factura.pdf", result, avisos,
                           contenido.escaneado)
    logger.info(
        "factura procesada",
        extra={
            "factura_id": row.id,
            "modelo": result.modelo,
            "tokens_entrada": result.tokens_entrada,
            "tokens_salida": result.tokens_salida,
            "coste_eur": result.coste_eur,
            "tiempo_ms": result.tiempo_ms,
            "avisos": len(avisos),
        },
    )
    return repository.to_read(row)


@app.get("/facturas", response_model=FacturaList, tags=["facturas"])
def listar_facturas(
    db: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    emisor: Annotated[str | None, Query(description="Nombre o NIF del emisor")] = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> FacturaList:
    rows, total = repository.listar(db, page, size, emisor, desde, hasta)
    return FacturaList(
        items=[repository.to_read(r) for r in rows], total=total, page=page, size=size
    )


# Debe declararse antes de /facturas/{factura_id}
@app.get("/facturas/export.xlsx", tags=["facturas"])
def exportar_excel(db: DbSession) -> Response:
    contenido = to_xlsx(repository.todas(db))
    return Response(
        contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="facturas.xlsx"'},
    )


@app.get("/facturas/{factura_id}", response_model=FacturaRead, tags=["facturas"])
def obtener_factura(factura_id: int, db: DbSession) -> FacturaRead:
    row = repository.obtener(db, factura_id)
    if row is None:
        raise HTTPException(404, "Factura no encontrada")
    return repository.to_read(row)


@app.patch("/facturas/{factura_id}", response_model=FacturaRead, tags=["facturas"])
def corregir_factura(factura_id: int, cambios: FacturaPatch, db: DbSession) -> FacturaRead:
    row = repository.obtener(db, factura_id)
    if row is None:
        raise HTTPException(404, "Factura no encontrada")

    datos = repository.to_factura(row).model_dump()
    datos.update(cambios.model_dump(exclude_unset=True, exclude={"confirmar"}))
    try:
        factura = Factura.model_validate(datos)
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False)) from exc

    avisos = validar_factura(factura)
    row = repository.actualizar(db, row, factura, avisos, cambios.confirmar)
    return repository.to_read(row)
