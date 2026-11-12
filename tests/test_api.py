import io

from openpyxl import load_workbook

from app import main


def subir(client, contenido: bytes, nombre="factura.pdf", tipo="application/pdf"):
    return client.post("/facturas", files={"archivo": (nombre, contenido, tipo)})


def test_subir_factura(client, pdf_bytes):
    r = subir(client, pdf_bytes)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["estado"] == "procesada"
    assert body["avisos"] == []
    assert body["datos"]["emisor"]["nif"] == "B12345674"
    assert body["datos"]["lineas"][0]["importe"] == 500.0
    assert body["tokens_entrada"] == 1200
    assert body["escaneada"] is False
    assert "F2026-0001" in client.extract_calls[0].texto

    pasos = body["pasos"]
    assert [p["nombre"] for p in pasos] == [
        "Validação do arquivo", "Leitura do PDF", "Extração de dados",
        "Validação das regras de negócio", "Armazenamento",
    ]
    assert all(p["estado"] == "ok" for p in pasos)
    assert "PDF digital" in pasos[1]["detalle"]
    assert len(body["reglas"]) == 8 and all(r["ok"] for r in body["reglas"])


def test_pasos_y_reglas_con_avisos(client, pdf_bytes, monkeypatch, factura):
    from app.llm_extractor import ExtractionResult

    mala = factura.model_copy(update={"total": 900.0})
    monkeypatch.setattr(main, "extract", lambda c, model=None: ExtractionResult(
        factura=mala, modelo="demo", tokens_entrada=0, tokens_salida=0, coste_eur=0,
        tiempo_ms=1))
    body = subir(client, pdf_bytes).json()
    assert body["estado"] == "con_avisos"
    assert body["pasos"][3]["estado"] == "aviso"
    assert "7 de 8" in body["pasos"][3]["detalle"]
    falladas = [r for r in body["reglas"] if not r["ok"]]
    assert [r["nombre"] for r in falladas] == ["Base + IVA − IRPF = total"]
    assert "900.00" in falladas[0]["detalle"]
    assert client.get(f"/facturas/{body['id']}").json()["pasos"] == []


def test_rechaza_no_pdf(client):
    r = subir(client, b"hola", nombre="nota.txt", tipo="text/plain")
    assert r.status_code == 422
    assert "PDF" in r.json()["detail"]


def test_rechaza_pdf_falso(client):
    assert subir(client, b"no soy un pdf").status_code == 422


def test_rechaza_archivo_grande(client, monkeypatch):
    monkeypatch.setattr(main.settings, "max_upload_mb", 1)
    r = subir(client, b"%PDF" + b"0" * (1024 * 1024))
    assert r.status_code == 422
    assert "1 MB" in r.json()["detail"]


def test_limite_por_ip(client, pdf_bytes, monkeypatch):
    monkeypatch.setattr(main.rate_limiter, "limit", 2)
    assert subir(client, pdf_bytes).status_code == 201
    assert subir(client, pdf_bytes).status_code == 201
    assert subir(client, pdf_bytes).status_code == 429


def test_listar_y_filtrar(client, pdf_bytes):
    subir(client, pdf_bytes)
    subir(client, pdf_bytes)
    r = client.get("/facturas", params={"emisor": "consultora", "size": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2 and len(body["items"]) == 1
    assert client.get("/facturas", params={"emisor": "otra"}).json()["total"] == 0
    assert client.get("/facturas", params={"desde": "2026-04-01"}).json()["total"] == 0
    assert client.get("/facturas", params={"hasta": "2026-03-31"}).json()["total"] == 2


def test_detalle_y_404(client, pdf_bytes):
    fid = subir(client, pdf_bytes).json()["id"]
    assert client.get(f"/facturas/{fid}").json()["id"] == fid
    assert client.get("/facturas/999").status_code == 404


def test_patch_revalida_y_confirma(client, pdf_bytes):
    fid = subir(client, pdf_bytes).json()["id"]

    r = client.patch(f"/facturas/{fid}", json={"total": 800.0})
    assert r.status_code == 200
    assert r.json()["estado"] == "con_avisos"
    assert [a["campo"] for a in r.json()["avisos"]] == ["total"]

    r = client.patch(f"/facturas/{fid}", json={"total": 795.0, "confirmar": True})
    assert r.json()["estado"] == "revisada"
    assert r.json()["avisos"] == []
    assert len(r.json()["datos"]["lineas"]) == 2


def test_patch_invalido(client, pdf_bytes):
    fid = subir(client, pdf_bytes).json()["id"]
    r = client.patch(f"/facturas/{fid}", json={"fecha_emision": "no-es-fecha"})
    assert r.status_code == 422


def test_exportar_excel(client, pdf_bytes):
    subir(client, pdf_bytes)
    r = client.get("/facturas/export.xlsx")
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Faturas", "Linhas"]
    ws = wb["Faturas"]
    assert ws["B2"].value == "F2026-0001"
    assert ws["A1"].font.bold
    assert ws["C2"].number_format == "DD/MM/YYYY"
    assert "€" in ws["L2"].number_format
    assert ws["M2"].value == "Processada"
    assert wb["Linhas"].max_row == 3
