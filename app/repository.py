"""Acceso a datos: traduce entre el esquema Pydantic y las tablas SQLAlchemy."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.llm_extractor import ExtractionResult
from app.models import FacturaDB, LineaFacturaDB
from app.schemas import Aviso, Empresa, Estado, Factura, FacturaRead, LineaFactura
from app.validators import resumen_reglas


def _estado(avisos: list[Aviso]) -> Estado:
    return Estado.con_avisos if avisos else Estado.procesada


def _aplicar_datos(row: FacturaDB, f: Factura) -> None:
    row.numero = f.numero
    row.fecha_emision = f.fecha_emision
    row.emisor_nombre = f.emisor.nombre
    row.emisor_nif = f.emisor.nif
    row.receptor_nombre = f.receptor.nombre
    row.receptor_nif = f.receptor.nif
    row.base_imponible = f.base_imponible
    row.tipo_iva = f.tipo_iva
    row.cuota_iva = f.cuota_iva
    row.retencion_irpf = f.retencion_irpf
    row.total = f.total
    row.lineas = [
        LineaFacturaDB(
            orden=i,
            descripcion=linea.descripcion,
            cantidad=linea.cantidad,
            precio_unitario=linea.precio_unitario,
            importe=linea.importe,
        )
        for i, linea in enumerate(f.lineas)
    ]


def to_factura(row: FacturaDB) -> Factura:
    return Factura(
        numero=row.numero,
        fecha_emision=row.fecha_emision,
        emisor=Empresa(nombre=row.emisor_nombre, nif=row.emisor_nif),
        receptor=Empresa(nombre=row.receptor_nombre, nif=row.receptor_nif),
        lineas=[
            LineaFactura(
                descripcion=linea.descripcion,
                cantidad=float(linea.cantidad),
                precio_unitario=float(linea.precio_unitario),
                importe=float(linea.importe),
            )
            for linea in row.lineas
        ],
        base_imponible=float(row.base_imponible),
        tipo_iva=float(row.tipo_iva),
        cuota_iva=float(row.cuota_iva),
        retencion_irpf=None if row.retencion_irpf is None else float(row.retencion_irpf),
        total=float(row.total),
    )


def to_read(row: FacturaDB) -> FacturaRead:
    avisos = [Aviso.model_validate(a) for a in row.avisos or []]
    return FacturaRead(
        id=row.id,
        estado=Estado(row.estado),
        datos=to_factura(row),
        avisos=avisos,
        reglas=resumen_reglas(avisos),
        archivo=row.archivo,
        modelo=row.modelo,
        tokens_entrada=row.tokens_entrada,
        tokens_salida=row.tokens_salida,
        coste_eur=float(row.coste_eur),
        tiempo_ms=row.tiempo_ms,
        escaneada=row.escaneada,
        creada_en=row.creada_en,
    )


def crear(
    db: Session, archivo: str, result: ExtractionResult, avisos: list[Aviso], escaneada: bool
) -> FacturaDB:
    row = FacturaDB(
        estado=_estado(avisos),
        archivo=archivo,
        avisos=[a.model_dump(mode="json") for a in avisos],
        modelo=result.modelo,
        tokens_entrada=result.tokens_entrada,
        tokens_salida=result.tokens_salida,
        coste_eur=result.coste_eur,
        tiempo_ms=result.tiempo_ms,
        escaneada=escaneada,
    )
    _aplicar_datos(row, result.factura)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def obtener(db: Session, factura_id: int) -> FacturaDB | None:
    return db.get(FacturaDB, factura_id)


def listar(
    db: Session,
    page: int = 1,
    size: int = 20,
    emisor: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> tuple[list[FacturaDB], int]:
    stmt = select(FacturaDB)
    if emisor:
        patron = f"%{emisor}%"
        stmt = stmt.where(
            FacturaDB.emisor_nombre.ilike(patron) | FacturaDB.emisor_nif.ilike(patron)
        )
    if desde:
        stmt = stmt.where(FacturaDB.fecha_emision >= desde)
    if hasta:
        stmt = stmt.where(FacturaDB.fecha_emision <= hasta)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(FacturaDB.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return list(rows), total


def todas(db: Session) -> list[FacturaDB]:
    return list(db.scalars(select(FacturaDB).order_by(FacturaDB.id)).all())


def actualizar(
    db: Session, row: FacturaDB, factura: Factura, avisos: list[Aviso], confirmar: bool
) -> FacturaDB:
    _aplicar_datos(row, factura)
    row.avisos = [a.model_dump(mode="json") for a in avisos]
    row.estado = Estado.revisada if confirmar else _estado(avisos)
    db.commit()
    db.refresh(row)
    return row
