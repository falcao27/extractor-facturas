"""Evalúa la extracción campo a campo contra el dataset de referencia.

Uso: python -m eval.run_eval --models claude-haiku-5-5 claude-sonnet-5-5

Las respuestas se guardan en eval/cache/<modelo>/ para no pagar dos veces la misma factura
(usa --no-cache para repetir). Escribe la tabla comparativa en eval/results.md.
"""

import argparse
import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path

from app.llm_extractor import ExtractionError, extract
from app.pdf_reader import read_pdf
from app.schemas import Factura
from app.validators import validar_factura

DATASET = Path("eval/dataset")
CACHE = Path("eval/cache")
RESULTS = Path("eval/results.md")
TOL = 0.01


def norm_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", value.lower())


def num_eq(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return (a or 0) == (b or 0)  # null y 0 de IRPF son equivalentes
    return abs(a - b) <= TOL


def lineas_eq(pred: list[dict], ref: list[dict]) -> bool:
    return len(pred) == len(ref) and all(
        norm_text(p["descripcion"]) == norm_text(r["descripcion"])
        and num_eq(p["cantidad"], r["cantidad"])
        and num_eq(p["precio_unitario"], r["precio_unitario"])
        and num_eq(p["importe"], r["importe"])
        for p, r in zip(pred, ref, strict=True)
    )


CAMPOS: dict[str, Callable[[dict, dict], bool]] = {
    "Número": lambda p, r: norm_text(p["numero"]) == norm_text(r["numero"]),
    "Fecha emisión": lambda p, r: p["fecha_emision"] == r["fecha_emision"],
    "Emisor nombre": lambda p, r: norm_text(p["emisor"]["nombre"])
    == norm_text(r["emisor"]["nombre"]),
    "NIF emisor": lambda p, r: norm_text(p["emisor"]["nif"]) == norm_text(r["emisor"]["nif"]),
    "Receptor nombre": lambda p, r: norm_text(p["receptor"]["nombre"])
    == norm_text(r["receptor"]["nombre"]),
    "NIF receptor": lambda p, r: norm_text(p["receptor"]["nif"]) == norm_text(r["receptor"]["nif"]),
    "Líneas (todas)": lambda p, r: lineas_eq(p["lineas"], r["lineas"]),
    "Base imponible": lambda p, r: num_eq(p["base_imponible"], r["base_imponible"]),
    "Tipo IVA": lambda p, r: num_eq(p["tipo_iva"], r["tipo_iva"]),
    "Cuota IVA": lambda p, r: num_eq(p["cuota_iva"], r["cuota_iva"]),
    "Retención IRPF": lambda p, r: num_eq(p["retencion_irpf"], r["retencion_irpf"]),
    "Total": lambda p, r: num_eq(p["total"], r["total"]),
}


def extraer_con_cache(pdf_path: Path, model: str, use_cache: bool) -> dict | None:
    cache_file = CACHE / model / f"{pdf_path.stem}.json"
    if use_cache and cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    try:
        result = extract(read_pdf(pdf_path), model=model)
    except ExtractionError as exc:
        print(f"  ! {pdf_path.name}: {exc}")
        return None
    data = {
        "factura": result.factura.model_dump(mode="json"),
        "tokens_entrada": result.tokens_entrada,
        "tokens_salida": result.tokens_salida,
        "coste_eur": result.coste_eur,
        "tiempo_ms": result.tiempo_ms,
    }
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def evaluar(model: str, use_cache: bool) -> dict:
    aciertos = dict.fromkeys(CAMPOS, 0)
    n = fallos_api = trampas = trampas_detectadas = falsos_avisos = 0
    costes, tiempos, errores = [], [], []

    for ref_file in sorted(DATASET.glob("*.json")):
        ref = json.loads(ref_file.read_text(encoding="utf-8"))
        n += 1
        out = extraer_con_cache(ref_file.with_suffix(".pdf"), model, use_cache)
        if out is None:
            fallos_api += 1
            continue
        pred = out["factura"]
        costes.append(out["coste_eur"])
        tiempos.append(out["tiempo_ms"])
        for campo, cmp in CAMPOS.items():
            if cmp(pred, ref["datos"]):
                aciertos[campo] += 1
            else:
                errores.append(f"{ref_file.stem} · {campo}")

        avisos = validar_factura(Factura.model_validate(pred))
        if ref["meta"]["trampa"]:
            trampas += 1
            trampas_detectadas += bool(avisos)
        elif avisos:
            falsos_avisos += 1

    return {
        "model": model,
        "n": n,
        "precision": {c: aciertos[c] / n for c in CAMPOS},
        "coste_medio": sum(costes) / len(costes) if costes else 0.0,
        "tiempo_medio_ms": sum(tiempos) / len(tiempos) if tiempos else 0.0,
        "fallos_api": fallos_api,
        "trampas": f"{trampas_detectadas}/{trampas}",
        "falsos_avisos": falsos_avisos,
        "errores": errores,
    }


def tabla_markdown(resultados: list[dict]) -> str:
    cab = "| Campo | " + " | ".join(r["model"] for r in resultados) + " |"
    sep = "|---|" + "---:|" * len(resultados)
    filas = [cab, sep]
    for campo in CAMPOS:
        filas.append(
            f"| {campo} | " + " | ".join(f"{r['precision'][campo]:.0%}" for r in resultados) + " |"
        )
    filas.append(
        "| **Media de campos** | "
        + " | ".join(
            f"**{sum(r['precision'].values()) / len(CAMPOS):.1%}**" for r in resultados
        )
        + " |"
    )
    filas.append("| Coste medio por factura | "
                 + " | ".join(f"{r['coste_medio']:.5f} €" for r in resultados) + " |")
    filas.append("| Tiempo medio | "
                 + " | ".join(f"{r['tiempo_medio_ms'] / 1000:.1f} s" for r in resultados) + " |")
    filas.append("| Trampas detectadas por las reglas | "
                 + " | ".join(r["trampas"] for r in resultados) + " |")
    filas.append("| Avisos en facturas correctas | "
                 + " | ".join(str(r["falsos_avisos"]) for r in resultados) + " |")
    filas.append("| Fallos de extracción | "
                 + " | ".join(str(r["fallos_api"]) for r in resultados) + " |")
    return "\n".join(filas)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=["claude-haiku-5-5"])
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()

    resultados = []
    for model in args.models:
        print(f"Evaluando {model}...")
        resultados.append(evaluar(model, use_cache=not args.no_cache))

    tabla = tabla_markdown(resultados)
    print("\n" + tabla)
    for r in resultados:
        if r["errores"]:
            print(f"\nErrores de {r['model']}:\n  " + "\n  ".join(r["errores"]))
    RESULTS.write_text(
        f"# Resultados de la evaluación ({resultados[0]['n']} facturas)\n\n{tabla}\n",
        encoding="utf-8",
    )
    print(f"\nTabla guardada en {RESULTS}")


if __name__ == "__main__":
    main()
