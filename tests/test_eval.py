from eval.generate_invoices import eur_es, generar
from eval.run_eval import CAMPOS, num_eq, tabla_markdown


def test_formato_espanol():
    from decimal import Decimal

    assert eur_es(Decimal("1234.5")) == "1.234,50"
    assert eur_es(Decimal("-1234567.89")) == "-1.234.567,89"
    assert eur_es(Decimal("0.07")) == "0,07"


def test_generar_dataset(tmp_path):
    archivos = generar(6, tmp_path, seed=1)
    assert len(archivos) == 6
    assert len(list(tmp_path.glob("*.json"))) == 6


def test_comparacion(datos):
    assert all(cmp(datos, datos) for cmp in CAMPOS.values())
    otro = {**datos, "total": datos["total"] + 0.5}
    assert not CAMPOS["Total"](otro, datos)
    assert num_eq(None, 0.0)


def test_tabla_markdown():
    res = {
        "model": "m", "n": 1, "precision": dict.fromkeys(CAMPOS, 1.0), "coste_medio": 0.0001,
        "tiempo_medio_ms": 1500, "fallos_api": 0, "trampas": "1/1", "falsos_avisos": 0,
    }
    tabla = tabla_markdown([res])
    assert "| Total | 100% |" in tabla
    assert "100.0%" in tabla
