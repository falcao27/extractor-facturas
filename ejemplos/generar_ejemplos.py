"""Crea dos facturas ficticias para probar la interfaz (también en modo demo).

Uso: python -m ejemplos.generar_ejemplos

- factura_prueba_correcta.pdf: todo cuadra, con retención de IRPF
- factura_prueba_con_errores.pdf: NIF del receptor inválido y cuota de IVA mal calculada
"""

import json
from pathlib import Path

from eval.generate_invoices import dibujar

CARPETA = Path(__file__).resolve().parent

EJEMPLOS = {
    "factura_prueba_correcta": (
        {
            "numero": "SDL-2026-0147",
            "fecha_emision": "2026-10-28",
            "emisor": {"nombre": "Soluciones Digitales Levante S.L.", "nif": "B12345674"},
            "receptor": {"nombre": "Panadería Hermanos Ruiz S.A.", "nif": "A58818501"},
            "lineas": [
                {"descripcion": "Desarrollo de tienda online", "cantidad": 1,
                 "precio_unitario": 2400.0, "importe": 2400.0},
                {"descripcion": "Mantenimiento mensual", "cantidad": 6,
                 "precio_unitario": 85.5, "importe": 513.0},
                {"descripcion": "Alojamiento web", "cantidad": 12,
                 "precio_unitario": 9.95, "importe": 119.4},
            ],
            "base_imponible": 3032.4,
            "tipo_iva": 21.0,
            "cuota_iva": 636.8,
            "retencion_irpf": 454.86,
            "total": 3214.34,
        },
        ("Avenida del Puerto 112, 46023 Valencia", "Calle Mayor 8, 03001 Alicante"),
    ),
    "factura_prueba_con_errores": (
        {
            "numero": "SDL-2026-0152",
            "fecha_emision": "2026-11-05",
            "emisor": {"nombre": "Soluciones Digitales Levante S.L.", "nif": "B12345674"},
            "receptor": {"nombre": "Laura Martín Gómez", "nif": "12345678A"},
            "lineas": [
                {"descripcion": "Horas de consultoría", "cantidad": 8,
                 "precio_unitario": 60.0, "importe": 480.0},
                {"descripcion": "Formación presencial", "cantidad": 1,
                 "precio_unitario": 350.0, "importe": 350.0},
            ],
            "base_imponible": 830.0,
            "tipo_iva": 21.0,
            "cuota_iva": 147.3,  # correcto: 174,30 € (cifras transpuestas)
            "retencion_irpf": None,
            "total": 977.3,
        },
        ("Avenida del Puerto 112, 46023 Valencia", "Calle Colón 23, 46004 Valencia"),
    ),
}


def main() -> None:
    for nombre, (datos, direcciones) in EJEMPLOS.items():
        (CARPETA / f"{nombre}.pdf").write_bytes(dibujar(datos, layout=1, direcciones=direcciones))
        meta = {"layout": 1, "escaneada": False, "trampa": None}
        (CARPETA / f"{nombre}.json").write_text(
            json.dumps({"datos": datos, "meta": meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"{nombre}.pdf creado")


if __name__ == "__main__":
    main()
