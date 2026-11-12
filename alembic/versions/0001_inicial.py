"""Tablas facturas y lineas_factura

Revision ID: 0001
Revises:
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonType = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "facturas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("archivo", sa.String(255), nullable=False),
        sa.Column("numero", sa.String(100), nullable=False),
        sa.Column("fecha_emision", sa.Date(), nullable=False),
        sa.Column("emisor_nombre", sa.String(255), nullable=False),
        sa.Column("emisor_nif", sa.String(20), nullable=False),
        sa.Column("receptor_nombre", sa.String(255), nullable=False),
        sa.Column("receptor_nif", sa.String(20), nullable=False),
        sa.Column("base_imponible", sa.Numeric(14, 2), nullable=False),
        sa.Column("tipo_iva", sa.Numeric(5, 2), nullable=False),
        sa.Column("cuota_iva", sa.Numeric(14, 2), nullable=False),
        sa.Column("retencion_irpf", sa.Numeric(14, 2), nullable=True),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("avisos", JsonType, nullable=False),
        sa.Column("modelo", sa.String(50), nullable=False),
        sa.Column("tokens_entrada", sa.Integer(), nullable=False),
        sa.Column("tokens_salida", sa.Integer(), nullable=False),
        sa.Column("coste_eur", sa.Numeric(10, 6), nullable=False),
        sa.Column("tiempo_ms", sa.Integer(), nullable=False),
        sa.Column("escaneada", sa.Boolean(), nullable=False),
        sa.Column("creada_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("actualizada_en", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
    )
    op.create_index("ix_facturas_estado", "facturas", ["estado"])
    op.create_index("ix_facturas_fecha_emision", "facturas", ["fecha_emision"])
    op.create_index("ix_facturas_emisor_nombre", "facturas", ["emisor_nombre"])
    op.create_index("ix_facturas_emisor_nif", "facturas", ["emisor_nif"])

    op.create_table(
        "lineas_factura",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("factura_id", sa.Integer(),
                  sa.ForeignKey("facturas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.String(500), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("precio_unitario", sa.Numeric(14, 4), nullable=False),
        sa.Column("importe", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_lineas_factura_factura_id", "lineas_factura", ["factura_id"])


def downgrade() -> None:
    op.drop_table("lineas_factura")
    op.drop_table("facturas")
