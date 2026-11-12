"""Exportación a Excel: una hoja de facturas y otra de líneas."""

import io

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models import FacturaDB

FORMATO_EUR = '#,##0.00 "€"'
FORMATO_FECHA = "DD/MM/YYYY"
COLUMNAS_EUR = {"Base imponible", "Cuota IVA", "Retención IRPF", "Total", "Precio unitario",
                "Importe", "Coste (€)"}


def _facturas_df(rows: list[FacturaDB]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": r.id,
                "Número": r.numero,
                "Fecha": r.fecha_emision,
                "Emisor": r.emisor_nombre,
                "NIF emisor": r.emisor_nif,
                "Receptor": r.receptor_nombre,
                "NIF receptor": r.receptor_nif,
                "Base imponible": float(r.base_imponible),
                "Tipo IVA (%)": float(r.tipo_iva),
                "Cuota IVA": float(r.cuota_iva),
                "Retención IRPF": float(r.retencion_irpf or 0),
                "Total": float(r.total),
                "Estado": r.estado,
                "Avisos": "; ".join(a["mensaje"] for a in r.avisos or []),
                "Modelo": r.modelo,
                "Coste (€)": float(r.coste_eur),
            }
            for r in rows
        ],
        columns=[
            "ID", "Número", "Fecha", "Emisor", "NIF emisor", "Receptor", "NIF receptor",
            "Base imponible", "Tipo IVA (%)", "Cuota IVA", "Retención IRPF", "Total", "Estado",
            "Avisos", "Modelo", "Coste (€)",
        ],
    )


def _lineas_df(rows: list[FacturaDB]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID factura": r.id,
                "Número factura": r.numero,
                "Descripción": linea.descripcion,
                "Cantidad": float(linea.cantidad),
                "Precio unitario": float(linea.precio_unitario),
                "Importe": float(linea.importe),
            }
            for r in rows
            for linea in r.lineas
        ],
        columns=["ID factura", "Número factura", "Descripción", "Cantidad", "Precio unitario",
                 "Importe"],
    )


def _formatear(ws, df: pd.DataFrame) -> None:
    cabecera = PatternFill("solid", fgColor="DDEBF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = cabecera
    for idx, col in enumerate(df.columns, start=1):
        letra = get_column_letter(idx)
        ancho = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
        ws.column_dimensions[letra].width = min(ancho, 60)
        formato = FORMATO_EUR if col in COLUMNAS_EUR else FORMATO_FECHA if col == "Fecha" else None
        if formato:
            for (cell,) in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
                cell.number_format = formato
    ws.freeze_panes = "A2"


def to_xlsx(rows: list[FacturaDB]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nombre, df in (("Facturas", _facturas_df(rows)), ("Líneas", _lineas_df(rows))):
            df.to_excel(writer, sheet_name=nombre, index=False)
            _formatear(writer.sheets[nombre], df)
    return buffer.getvalue()
