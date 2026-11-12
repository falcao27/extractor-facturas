"""Exportação para Excel: uma aba de faturas e outra de linhas."""

import io

import pandas as pd
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from app.models import FacturaDB

FORMATO_EUR = '#,##0.00 "€"'
FORMATO_DATA = "DD/MM/YYYY"
COLUNAS_EUR = {"Base tributável", "Valor IVA", "Retenção IRPF", "Total", "Preço unitário",
               "Valor", "Custo (€)"}
STATUS = {"procesada": "Processada", "con_avisos": "Com avisos", "revisada": "Revisada",
          "error": "Erro"}

COLUNAS_FATURAS = [
    "ID", "Número", "Data", "Emissor", "NIF emissor", "Destinatário", "NIF destinatário",
    "Base tributável", "Alíquota IVA (%)", "Valor IVA", "Retenção IRPF", "Total", "Status",
    "Avisos", "Modelo", "Custo (€)",
]
COLUNAS_LINHAS = ["ID fatura", "Número fatura", "Descrição", "Quantidade", "Preço unitário",
                  "Valor"]


def _faturas_df(rows: list[FacturaDB]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": r.id,
                "Número": r.numero,
                "Data": r.fecha_emision,
                "Emissor": r.emisor_nombre,
                "NIF emissor": r.emisor_nif,
                "Destinatário": r.receptor_nombre,
                "NIF destinatário": r.receptor_nif,
                "Base tributável": float(r.base_imponible),
                "Alíquota IVA (%)": float(r.tipo_iva),
                "Valor IVA": float(r.cuota_iva),
                "Retenção IRPF": float(r.retencion_irpf or 0),
                "Total": float(r.total),
                "Status": STATUS.get(r.estado, r.estado),
                "Avisos": "; ".join(a["mensaje"] for a in r.avisos or []),
                "Modelo": r.modelo,
                "Custo (€)": float(r.coste_eur),
            }
            for r in rows
        ],
        columns=COLUNAS_FATURAS,
    )


def _linhas_df(rows: list[FacturaDB]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID fatura": r.id,
                "Número fatura": r.numero,
                "Descrição": linea.descripcion,
                "Quantidade": float(linea.cantidad),
                "Preço unitário": float(linea.precio_unitario),
                "Valor": float(linea.importe),
            }
            for r in rows
            for linea in r.lineas
        ],
        columns=COLUNAS_LINHAS,
    )


def _formatar(ws, df: pd.DataFrame) -> None:
    cabecalho = PatternFill("solid", fgColor="DDEBF7")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = cabecalho
    for idx, col in enumerate(df.columns, start=1):
        letra = get_column_letter(idx)
        largura = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
        ws.column_dimensions[letra].width = min(largura, 60)
        formato = FORMATO_EUR if col in COLUNAS_EUR else FORMATO_DATA if col == "Data" else None
        if formato:
            for (cell,) in ws.iter_rows(min_row=2, min_col=idx, max_col=idx):
                cell.number_format = formato
    ws.freeze_panes = "A2"


def to_xlsx(rows: list[FacturaDB]) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nome, df in (("Faturas", _faturas_df(rows)), ("Linhas", _linhas_df(rows))):
            df.to_excel(writer, sheet_name=nome, index=False)
            _formatar(writer.sheets[nome], df)
    return buffer.getvalue()
