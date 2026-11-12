"""Genera facturas ficticias en PDF con su JSON de referencia (gabarito).

Uso: python -m eval.generate_invoices [--n 30] [--out eval/dataset] [--seed 42]

- 3 diseños distintos (clásico, moderno con formato español 1.234,56 y compacto)
- con y sin IRPF, de 1 a 10 líneas
- algunas versiones escaneadas (página rasterizada con ligera rotación, sin capa de texto)
- algunas "trampa": NIF inválido o total erróneo, para comprobar que las reglas avisan
"""

import argparse
import io
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pdfplumber
from faker import Faker
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas

CENT = Decimal("0.01")
CONCEPTOS = [
    ("Horas de consultoría", 40, 95), ("Desarrollo de software", 30, 120),
    ("Licencia anual", 300, 1500), ("Mantenimiento mensual", 80, 400),
    ("Diseño gráfico", 150, 900), ("Material de oficina", 3, 40),
    ("Servicio de transporte", 50, 300), ("Auditoría contable", 400, 2000),
    ("Formación presencial", 200, 1200), ("Alojamiento web", 10, 60),
    ("Reparación de equipo", 45, 250), ("Traducción de documentos", 0.08, 0.15),
]


def q(value: Decimal | float) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def eur_es(value: Decimal) -> str:
    """1234.5 -> '1.234,50'"""
    entero, dec = f"{value:.2f}".split(".")
    signo = "-" if entero.startswith("-") else ""
    entero = entero.lstrip("-")
    grupos = []
    while entero:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    return f"{signo}{'.'.join(grupos)},{dec}"


def eur_en(value: Decimal) -> str:
    return f"{value:.2f}"


def romper_nif(nif: str) -> str:
    """Cambia la letra/dígito de control para que el NIF sea inválido."""
    ultimo = nif[-1]
    alternativas = "TRWAGMYFPDXBNJZSQVHLCKE" if ultimo.isalpha() else "0123456789"
    return nif[:-1] + next(c for c in alternativas if c != ultimo)


def generar_datos(fake: Faker, rng: random.Random, idx: int, trampa: str | None) -> dict:
    emisor_cif = fake.cif()
    receptor_nif = fake.nif() if rng.random() < 0.4 else fake.cif()
    con_irpf = rng.random() < 0.35
    tipo_iva = rng.choice([21, 21, 21, 10, 4])
    lineas = []
    for _ in range(rng.randint(1, 10)):
        concepto, pmin, pmax = rng.choice(CONCEPTOS)
        cantidad = rng.choice([1, 1, 2, 3, 5, 10, 12, 20]) if pmax > 1 else rng.randint(500, 5000)
        precio = q(rng.uniform(pmin, pmax))
        lineas.append(
            {
                "descripcion": concepto,
                "cantidad": cantidad,
                "precio_unitario": float(precio),
                "importe": float(q(precio * cantidad)),
            }
        )
    base = sum((q(linea["importe"]) for linea in lineas), Decimal(0))
    cuota = q(base * tipo_iva / 100)
    irpf = q(base * 15 / 100) if con_irpf else None
    total = base + cuota - (irpf or 0)

    datos = {
        "numero": rng.choice([f"F{2026}-{idx:04d}", f"{2026}/{idx:03d}", f"FAC-{idx:05d}"]),
        "fecha_emision": (date(2026, 1, 1) + timedelta(days=rng.randint(0, 300))).isoformat(),
        "emisor": {"nombre": fake.company(), "nif": emisor_cif},
        "receptor": {
            "nombre": fake.name() if receptor_nif[0].isdigit() else fake.company(),
            "nif": receptor_nif,
        },
        "lineas": lineas,
        "base_imponible": float(base),
        "tipo_iva": float(tipo_iva),
        "cuota_iva": float(cuota),
        "retencion_irpf": float(irpf) if irpf is not None else None,
        "total": float(total),
    }
    if trampa == "nif":
        datos["emisor"]["nif"] = romper_nif(emisor_cif)
    elif trampa == "total":
        datos["total"] = float(total + Decimal("10.00"))
    return datos


def _texto(c: Canvas, x: float, y: float, txt: str, size: int = 10, bold: bool = False,
           right: bool = False) -> None:
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    (c.drawRightString if right else c.drawString)(x, y, txt)


def dibujar(datos: dict, layout: int, direcciones: tuple[str, str]) -> bytes:
    buffer = io.BytesIO()
    c = Canvas(buffer, pagesize=A4)
    w, h = A4
    fmt = eur_es if layout == 1 else eur_en
    fecha = date.fromisoformat(datos["fecha_emision"])
    fecha_txt = fecha.strftime("%d/%m/%Y") if layout != 2 else fecha.strftime("%d-%m-%Y")
    em, re_ = datos["emisor"], datos["receptor"]

    if layout == 0:  # clásico
        _texto(c, 20 * mm, h - 25 * mm, em["nombre"], 14, bold=True)
        _texto(c, 20 * mm, h - 31 * mm, f"CIF: {em['nif']}")
        _texto(c, 20 * mm, h - 36 * mm, direcciones[0][:80], 9)
        _texto(c, w - 20 * mm, h - 25 * mm, "FACTURA", 18, bold=True, right=True)
        _texto(c, w - 20 * mm, h - 32 * mm, f"Nº factura: {datos['numero']}", right=True)
        _texto(c, w - 20 * mm, h - 37 * mm, f"Fecha: {fecha_txt}", right=True)
        _texto(c, 20 * mm, h - 52 * mm, "Facturar a:", bold=True)
        _texto(c, 20 * mm, h - 58 * mm, re_["nombre"])
        _texto(c, 20 * mm, h - 63 * mm, f"NIF: {re_['nif']}")
        _texto(c, 20 * mm, h - 68 * mm, direcciones[1][:80], 9)
        y = h - 85 * mm
    elif layout == 1:  # moderno, banda de color y formato español
        c.setFillColor(colors.HexColor("#1F4E79"))
        c.rect(0, h - 40 * mm, w, 40 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        _texto(c, 20 * mm, h - 20 * mm, em["nombre"], 16, bold=True)
        _texto(c, 20 * mm, h - 28 * mm, f"NIF {em['nif']} · {direcciones[0][:60]}", 9)
        _texto(c, w - 20 * mm, h - 20 * mm, f"Factura {datos['numero']}", 12, bold=True,
               right=True)
        _texto(c, w - 20 * mm, h - 28 * mm, f"Emitida el {fecha_txt}", 10, right=True)
        c.setFillColor(colors.black)
        _texto(c, 20 * mm, h - 55 * mm, "CLIENTE", 9, bold=True)
        _texto(c, 20 * mm, h - 61 * mm, f"{re_['nombre']} — {re_['nif']}")
        _texto(c, 20 * mm, h - 66 * mm, direcciones[1][:80], 9)
        y = h - 82 * mm
    else:  # compacto, datos en bloque
        _texto(c, 20 * mm, h - 20 * mm, f"FACTURA N.º {datos['numero']}    FECHA {fecha_txt}", 11,
               bold=True)
        _texto(c, 20 * mm, h - 30 * mm, f"Emisor: {em['nombre']}   CIF/NIF: {em['nif']}", 9)
        _texto(c, 20 * mm, h - 35 * mm, f"Cliente: {re_['nombre']}   CIF/NIF: {re_['nif']}", 9)
        y = h - 48 * mm

    cols = [20 * mm, 110 * mm, 140 * mm, w - 20 * mm]
    c.setStrokeColor(colors.grey)
    c.line(20 * mm, y + 4 * mm, w - 20 * mm, y + 4 * mm)
    _texto(c, cols[0], y, "Descripción", bold=True)
    _texto(c, cols[1], y, "Cant.", bold=True)
    _texto(c, cols[2], y, "Precio", bold=True)
    _texto(c, cols[3], y, "Importe", bold=True, right=True)
    y -= 2 * mm
    c.line(20 * mm, y, w - 20 * mm, y)
    y -= 6 * mm
    for linea in datos["lineas"]:
        cantidad = linea["cantidad"]
        _texto(c, cols[0], y, linea["descripcion"])
        _texto(c, cols[1], y, str(int(cantidad)) if float(cantidad).is_integer() else str(cantidad))
        _texto(c, cols[2], y, fmt(q(linea["precio_unitario"])))
        _texto(c, cols[3], y, fmt(q(linea["importe"])), right=True)
        y -= 6 * mm
    c.line(110 * mm, y + 2 * mm, w - 20 * mm, y + 2 * mm)
    y -= 4 * mm

    resumen = [
        ("Base imponible", q(datos["base_imponible"])),
        (f"IVA {datos['tipo_iva']:g}%", q(datos["cuota_iva"])),
    ]
    if datos["retencion_irpf"] is not None:
        resumen.append(("Retención IRPF 15%", -q(datos["retencion_irpf"])))
    resumen.append(("TOTAL", q(datos["total"])))
    for etiqueta, valor in resumen:
        negrita = etiqueta == "TOTAL"
        _texto(c, 140 * mm, y, etiqueta, 11 if negrita else 10, bold=negrita)
        _texto(c, cols[3], y, f"{fmt(valor)} €", 11 if negrita else 10, bold=negrita, right=True)
        y -= 6 * mm

    _texto(c, 20 * mm, 15 * mm, "Forma de pago: transferencia bancaria a 30 días.", 8)
    c.showPage()
    c.save()
    return buffer.getvalue()


def escanear(pdf_bytes: bytes, rng: random.Random) -> bytes:
    """Rasteriza la página, la rota ligeramente y la guarda como PDF sin texto."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        img = pdf.pages[0].to_image(resolution=110).original.convert("L")
    img = img.rotate(rng.uniform(-1.5, 1.5), expand=True, fillcolor=255, resample=Image.BICUBIC)
    out = io.BytesIO()
    img.convert("RGB").save(out, format="PDF", resolution=110)
    return out.getvalue()


def generar(n: int, out: Path, seed: int) -> list[Path]:
    rng = random.Random(seed)
    fake = Faker("es_ES")
    Faker.seed(seed)
    out.mkdir(parents=True, exist_ok=True)

    indices = list(range(1, n + 1))
    escaneadas = set(rng.sample(indices, k=min(4, n)))
    resto = [i for i in indices if i not in escaneadas]
    trampas = dict(zip(rng.sample(resto, k=min(3, len(resto))), ["nif", "total", "nif"],
                       strict=False))

    generados = []
    for i in indices:
        trampa = trampas.get(i)
        datos = generar_datos(fake, rng, i, trampa)
        layout = (i - 1) % 3
        pdf = dibujar(datos, layout, (fake.address().replace("\n", ", "),
                                      fake.address().replace("\n", ", ")))
        if i in escaneadas:
            pdf = escanear(pdf, rng)
        nombre = f"factura_{i:03d}"
        (out / f"{nombre}.pdf").write_bytes(pdf)
        meta = {"layout": layout, "escaneada": i in escaneadas, "trampa": trampa}
        (out / f"{nombre}.json").write_text(
            json.dumps({"datos": datos, "meta": meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        generados.append(out / f"{nombre}.pdf")
    return generados


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=30)
    parser.add_argument("--out", type=Path, default=Path("eval/dataset"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    archivos = generar(args.n, args.out, args.seed)
    print(f"{len(archivos)} facturas generadas en {args.out}")


if __name__ == "__main__":
    main()
