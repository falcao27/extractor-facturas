"""Reglas de negocio. Cada regla genera un aviso, nunca bloquea la factura."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.schemas import Aviso, Factura, ReglaResultado, Severidad

LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
LETRAS_CIF = "ABCDEFGHJNPQRSUVW"
CONTROL_CIF_LETRA = "JABCDEFGHI"
TIPOS_IVA = {Decimal(21), Decimal(10), Decimal(4), Decimal(0)}
TOLERANCIA = Decimal("0.02")
CENT = Decimal("0.01")


# Regla visible -> campos de aviso que la incumplen ("x[" = prefijo, resto = exacto)
REGLAS: list[tuple[str, tuple[str, ...]]] = [
    ("NIF/CIF do emissor válido", ("emisor.nif",)),
    ("NIF/CIF do destinatário válido", ("receptor.nif",)),
    ("Cada linha: quantidade × preço = valor", ("lineas[",)),
    ("Soma das linhas = base tributável", ("base_imponible", "lineas")),
    ("Alíquota de IVA permitida (21, 10, 4 ou 0 %)", ("tipo_iva",)),
    ("Base × alíquota de IVA = valor do IVA", ("cuota_iva",)),
    ("Base + IVA − IRPF = total", ("total",)),
    ("Data de emissão não futura", ("fecha_emision",)),
]


def _coincide(campo: str, claves: tuple[str, ...]) -> bool:
    return any(campo.startswith(c) if c.endswith("[") else campo == c for c in claves)


def resumen_reglas(avisos: list[Aviso]) -> list[ReglaResultado]:
    """Checklist de todas las reglas comprobadas, a partir de los avisos generados."""
    resultado = []
    for nombre, claves in REGLAS:
        fallos = [a.mensaje for a in avisos if _coincide(a.campo, claves)]
        resultado.append(ReglaResultado(nombre=nombre, ok=not fallos, detalle="; ".join(fallos)))
    return resultado


def normalizar_nif(doc: str) -> str:
    doc = re.sub(r"[\s\-.]", "", doc.upper())
    return doc[2:] if doc.startswith("ES") and len(doc) == 11 else doc


def validar_dni_nie(doc: str) -> bool:
    doc = normalizar_nif(doc)
    if len(doc) != 9:
        return False
    if doc[0] in "XYZ":
        doc = str("XYZ".index(doc[0])) + doc[1:]
    numero, letra = doc[:8], doc[8]
    return numero.isdigit() and LETRAS_DNI[int(numero) % 23] == letra


def validar_cif(cif: str) -> bool:
    cif = normalizar_nif(cif)
    if len(cif) != 9 or cif[0] not in LETRAS_CIF or not cif[1:8].isdigit():
        return False
    d = cif[1:8]
    pares = sum(int(d[i]) for i in (1, 3, 5))
    impares = sum(sum(divmod(int(d[i]) * 2, 10)) for i in (0, 2, 4, 6))
    control = (10 - (pares + impares) % 10) % 10
    return cif[8] in (str(control), CONTROL_CIF_LETRA[control])


def validar_nif(doc: str) -> bool:
    """Acepta DNI, NIE o CIF."""
    doc = normalizar_nif(doc)
    if doc[:1] in LETRAS_CIF:
        return validar_cif(doc)
    return validar_dni_nie(doc)


def _d(value: float | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _eur(value: Decimal) -> str:
    return f"{value:.2f} €"


def _pct(value: Decimal) -> str:
    return f"{value:f}".rstrip("0").rstrip(".") if "." in f"{value:f}" else f"{value:f}"


def validar_factura(f: Factura, hoy: date | None = None) -> list[Aviso]:
    hoy = hoy or date.today()
    avisos: list[Aviso] = []

    for campo, empresa in (("emisor.nif", f.emisor), ("receptor.nif", f.receptor)):
        if not validar_nif(empresa.nif):
            avisos.append(Aviso(campo=campo, mensaje=f"NIF/CIF inválido: {empresa.nif}"))

    base = _d(f.base_imponible)
    cuota = _d(f.cuota_iva)
    irpf = _d(f.retencion_irpf)
    tipo = Decimal(str(f.tipo_iva))

    if f.lineas:
        suma = sum((_d(linea.importe) for linea in f.lineas), Decimal(0))
        if abs(suma - base) > TOLERANCIA:
            avisos.append(
                Aviso(
                    campo="base_imponible",
                    mensaje=f"A soma das linhas ({_eur(suma)}) não confere com a base "
                    f"tributável ({_eur(base)})",
                )
            )
        for i, linea in enumerate(f.lineas):
            esperado = _d(linea.cantidad * linea.precio_unitario)
            if abs(esperado - _d(linea.importe)) > TOLERANCIA:
                avisos.append(
                    Aviso(
                        campo=f"lineas[{i}].importe",
                        mensaje=f"Quantidade × preço ({_eur(esperado)}) não confere com o "
                        f"valor ({_eur(_d(linea.importe))})",
                    )
                )
    else:
        avisos.append(Aviso(campo="lineas", mensaje="A fatura não tem linhas de detalhe"))

    if tipo not in TIPOS_IVA:
        avisos.append(
            Aviso(campo="tipo_iva", mensaje=f"Alíquota de IVA incomum: {_pct(tipo)} %")
        )

    cuota_esperada = (base * tipo / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(cuota_esperada - cuota) > TOLERANCIA:
        avisos.append(
            Aviso(
                campo="cuota_iva",
                mensaje=f"Base × {_pct(tipo)} % = {_eur(cuota_esperada)}, mas o IVA informado é "
                f"{_eur(cuota)}",
            )
        )

    total_esperado = base + cuota - irpf
    if abs(total_esperado - _d(f.total)) > TOLERANCIA:
        avisos.append(
            Aviso(
                campo="total",
                mensaje=f"Base + IVA − IRPF = {_eur(total_esperado)}, mas o total é "
                f"{_eur(_d(f.total))}",
            )
        )

    if f.fecha_emision > hoy:
        avisos.append(
            Aviso(
                campo="fecha_emision",
                mensaje=f"A data de emissão ({f.fecha_emision:%d/%m/%Y}) está no futuro",
                severidad=Severidad.error,
            )
        )

    return avisos
