from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB en PostgreSQL, JSON genérico en SQLite (tests)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class FacturaDB(Base):
    __tablename__ = "facturas"

    id: Mapped[int] = mapped_column(primary_key=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)
    archivo: Mapped[str] = mapped_column(String(255))
    numero: Mapped[str] = mapped_column(String(100))
    fecha_emision: Mapped[date] = mapped_column(Date, index=True)
    emisor_nombre: Mapped[str] = mapped_column(String(255), index=True)
    emisor_nif: Mapped[str] = mapped_column(String(20), index=True)
    receptor_nombre: Mapped[str] = mapped_column(String(255))
    receptor_nif: Mapped[str] = mapped_column(String(20))
    base_imponible: Mapped[float] = mapped_column(Numeric(14, 2))
    tipo_iva: Mapped[float] = mapped_column(Numeric(5, 2))
    cuota_iva: Mapped[float] = mapped_column(Numeric(14, 2))
    retencion_irpf: Mapped[float | None] = mapped_column(Numeric(14, 2))
    total: Mapped[float] = mapped_column(Numeric(14, 2))
    avisos: Mapped[list] = mapped_column(JsonType, default=list)
    modelo: Mapped[str] = mapped_column(String(50))
    tokens_entrada: Mapped[int] = mapped_column(default=0)
    tokens_salida: Mapped[int] = mapped_column(default=0)
    coste_eur: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    tiempo_ms: Mapped[int] = mapped_column(default=0)
    escaneada: Mapped[bool] = mapped_column(default=False)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lineas: Mapped[list["LineaFacturaDB"]] = relationship(
        back_populates="factura",
        cascade="all, delete-orphan",
        order_by="LineaFacturaDB.orden",
        lazy="selectin",
    )


class LineaFacturaDB(Base):
    __tablename__ = "lineas_factura"

    id: Mapped[int] = mapped_column(primary_key=True)
    factura_id: Mapped[int] = mapped_column(
        ForeignKey("facturas.id", ondelete="CASCADE"), index=True
    )
    orden: Mapped[int]
    descripcion: Mapped[str] = mapped_column(String(500))
    cantidad: Mapped[float] = mapped_column(Numeric(14, 3))
    precio_unitario: Mapped[float] = mapped_column(Numeric(14, 4))
    importe: Mapped[float] = mapped_column(Numeric(14, 2))

    factura: Mapped[FacturaDB] = relationship(back_populates="lineas")
