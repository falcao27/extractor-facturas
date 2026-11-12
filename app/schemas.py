"""Modelos Pydantic: el mismo esquema sirve al LLM, a la API y a la evaluación.

Las descripciones de los campos se envían al LLM, así que forman parte del prompt.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Empresa(BaseModel):
    nombre: str = Field(
        description="Razón social o nombre completo, tal como aparece en la factura"
    )
    nif: str = Field(
        description=(
            "NIF, NIE o CIF en mayúsculas, sin espacios, guiones, puntos ni prefijo de país "
            "(por ejemplo B12345674, 12345678Z, X1234567L)"
        )
    )


class LineaFactura(BaseModel):
    descripcion: str = Field(description="Concepto de la línea")
    cantidad: float = Field(description="Unidades facturadas")
    precio_unitario: float = Field(description="Precio por unidad sin IVA, en euros")
    importe: float = Field(description="Importe de la línea sin IVA (cantidad × precio), en euros")


class Factura(BaseModel):
    numero: str = Field(description="Número o código de la factura, tal como aparece")
    fecha_emision: date = Field(description="Fecha de emisión (fecha de la factura)")
    emisor: Empresa = Field(description="Quien emite y cobra la factura (proveedor)")
    receptor: Empresa = Field(description="Cliente al que se factura")
    lineas: list[LineaFactura] = Field(description="Todas las líneas de detalle, en orden")
    base_imponible: float = Field(description="Base imponible total sin IVA, en euros")
    tipo_iva: float = Field(description="Porcentaje de IVA aplicado: 21, 10, 4 o 0")
    cuota_iva: float = Field(description="Importe del IVA en euros")
    retencion_irpf: float | None = Field(
        None,
        description=(
            "Importe retenido de IRPF en euros, como número positivo. "
            "null si la factura no tiene retención"
        ),
    )
    total: float = Field(description="Total a pagar de la factura, en euros")


class Severidad(StrEnum):
    error = "error"
    aviso = "aviso"


class Aviso(BaseModel):
    campo: str
    mensaje: str
    severidad: Severidad = Severidad.aviso


class Estado(StrEnum):
    procesada = "procesada"
    con_avisos = "con_avisos"
    revisada = "revisada"
    error = "error"


class FacturaRead(BaseModel):
    """Respuesta de la API: datos extraídos más metadatos del proceso."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    estado: Estado
    datos: Factura
    avisos: list[Aviso]
    archivo: str
    modelo: str
    tokens_entrada: int
    tokens_salida: int
    coste_eur: float
    tiempo_ms: int
    escaneada: bool
    creada_en: datetime


class FacturaPatch(BaseModel):
    """Corrección manual: solo los campos enviados se sustituyen."""

    numero: str | None = None
    fecha_emision: date | None = None
    emisor: Empresa | None = None
    receptor: Empresa | None = None
    lineas: list[LineaFactura] | None = None
    base_imponible: float | None = None
    tipo_iva: float | None = None
    cuota_iva: float | None = None
    retencion_irpf: float | None = None
    total: float | None = None
    confirmar: bool = Field(False, description="Marca la factura como revisada")


class FacturaList(BaseModel):
    items: list[FacturaRead]
    total: int
    page: int
    size: int
