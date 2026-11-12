"""Interfaz de demo: subir facturas, revisar avisos, corregir y descargar Excel."""

import os
from datetime import date
from pathlib import Path

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
EJEMPLO = Path(__file__).resolve().parents[1] / "eval" / "dataset" / "factura_010.pdf"
TIMEOUT = httpx.Timeout(120.0, connect=10.0)

st.set_page_config(page_title="Extractor de facturas con IA", page_icon="🧾", layout="wide")


def api(method: str, path: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError:
        st.error("No se pudo conectar con la API. Si es la demo gratuita, puede tardar "
                 "~1 minuto en despertar: inténtalo de nuevo.")
        return None
    if r.status_code >= 400:
        detalle = r.json().get("detail", r.text) if "json" in r.headers.get("content-type", "") \
            else r.text
        st.error(f"Error {r.status_code}: {detalle}")
        return None
    return r


def procesar(nombre: str, contenido: bytes) -> None:
    with st.spinner(f"Extrayendo {nombre}..."):
        r = api("POST", "/facturas", files={"archivo": (nombre, contenido, "application/pdf")})
    if r is not None:
        st.session_state.setdefault("procesadas", []).insert(0, r.json())


def avisos_de(factura: dict, prefijo: str) -> list[str]:
    return [a["mensaje"] for a in factura["avisos"] if a["campo"].startswith(prefijo)]


def campo_con_aviso(factura: dict, prefijo: str) -> None:
    for mensaje in avisos_de(factura, prefijo):
        st.warning(mensaje, icon="⚠️")


def formulario(factura: dict) -> None:
    d = factura["datos"]
    fid = factura["id"]
    estado = factura["estado"]
    color = {"procesada": "green", "con_avisos": "orange", "revisada": "blue"}.get(estado, "red")
    st.markdown(
        f"#### {factura['archivo']} · :{color}[{estado.replace('_', ' ')}]  \n"
        f"<small>{factura['modelo']} · {factura['tiempo_ms'] / 1000:.1f} s · "
        f"{factura['tokens_entrada'] + factura['tokens_salida']} tokens · "
        f"{factura['coste_eur']:.5f} €{' · escaneada' if factura['escaneada'] else ''}</small>",
        unsafe_allow_html=True,
    )

    with st.form(f"form_{fid}"):
        c1, c2 = st.columns(2)
        numero = c1.text_input("Número", d["numero"], key=f"num_{fid}")
        fecha = c2.date_input("Fecha de emisión", date.fromisoformat(d["fecha_emision"]),
                              format="DD/MM/YYYY", key=f"fecha_{fid}")
        campo_con_aviso(factura, "fecha_emision")

        c1, c2 = st.columns(2)
        emisor_nombre = c1.text_input("Emisor", d["emisor"]["nombre"], key=f"en_{fid}")
        emisor_nif = c2.text_input("NIF emisor", d["emisor"]["nif"], key=f"enif_{fid}")
        campo_con_aviso(factura, "emisor")
        c1, c2 = st.columns(2)
        receptor_nombre = c1.text_input("Receptor", d["receptor"]["nombre"], key=f"rn_{fid}")
        receptor_nif = c2.text_input("NIF receptor", d["receptor"]["nif"], key=f"rnif_{fid}")
        campo_con_aviso(factura, "receptor")

        st.markdown("**Líneas**")
        lineas = st.data_editor(
            d["lineas"], num_rows="dynamic", use_container_width=True, key=f"lineas_{fid}",
            column_config={
                "descripcion": st.column_config.TextColumn("Descripción", width="large"),
                "cantidad": st.column_config.NumberColumn("Cantidad"),
                "precio_unitario": st.column_config.NumberColumn("Precio unitario",
                                                                 format="%.2f €"),
                "importe": st.column_config.NumberColumn("Importe", format="%.2f €"),
            },
        )
        campo_con_aviso(factura, "lineas")

        c1, c2, c3, c4, c5 = st.columns(5)
        base = c1.number_input("Base imponible", value=d["base_imponible"], format="%.2f",
                               key=f"base_{fid}")
        tipo = c2.selectbox("Tipo IVA %", [21.0, 10.0, 4.0, 0.0],
                            index=[21.0, 10.0, 4.0, 0.0].index(d["tipo_iva"])
                            if d["tipo_iva"] in (21.0, 10.0, 4.0, 0.0) else 0,
                            key=f"tipo_{fid}")
        cuota = c3.number_input("Cuota IVA", value=d["cuota_iva"], format="%.2f",
                                key=f"cuota_{fid}")
        irpf = c4.number_input("Retención IRPF", value=d["retencion_irpf"] or 0.0,
                               format="%.2f", key=f"irpf_{fid}")
        total = c5.number_input("Total", value=d["total"], format="%.2f", key=f"total_{fid}")
        for prefijo in ("base_imponible", "tipo_iva", "cuota_iva", "total"):
            campo_con_aviso(factura, prefijo)

        c1, c2 = st.columns(2)
        guardar = c1.form_submit_button("Guardar corrección")
        confirmar = c2.form_submit_button("Confirmar ✅", type="primary")

    if guardar or confirmar:
        cambios = {
            "numero": numero,
            "fecha_emision": fecha.isoformat(),
            "emisor": {"nombre": emisor_nombre, "nif": emisor_nif},
            "receptor": {"nombre": receptor_nombre, "nif": receptor_nif},
            "lineas": [linea for linea in lineas if linea.get("descripcion")],
            "base_imponible": base,
            "tipo_iva": tipo,
            "cuota_iva": cuota,
            "retencion_irpf": irpf or None,
            "total": total,
            "confirmar": confirmar,
        }
        r = api("PATCH", f"/facturas/{fid}", json=cambios)
        if r is not None:
            procesadas = st.session_state["procesadas"]
            procesadas[:] = [r.json() if f["id"] == fid else f for f in procesadas]
            st.success("Factura revisada" if confirmar else "Corrección guardada")
            st.rerun()


st.title("🧾 Extractor de facturas con IA")
st.caption(
    "Sube facturas españolas en PDF: Claude extrae los datos, las reglas validan NIF/CIF, "
    "IVA, IRPF y totales, y puedes descargarlo todo en Excel. "
    "Los PDF no se guardan; usa solo facturas de prueba."
)

salud = api("GET", "/health")
if salud is not None and salud.json().get("llm_provider") == "demo":
    st.info(
        "**Modo demo (sin LLM, sin coste):** se reconocen las 30 facturas de `eval/dataset` y "
        "se devuelven sus datos de referencia. Validaciones, avisos, correcciones y Excel "
        "funcionan igual que con Claude.",
        icon="🧪",
    )

tab_subir, tab_historial = st.tabs(["Subir facturas", "Historial"])

with tab_subir:
    archivos = st.file_uploader("PDF de facturas (máx. 5 MB cada uno)", type=["pdf"],
                                accept_multiple_files=True)
    c1, c2 = st.columns([1, 1])
    if c1.button("Procesar", type="primary", disabled=not archivos):
        for archivo in archivos:
            procesar(archivo.name, archivo.getvalue())
    if c2.button("Probar con factura de ejemplo", disabled=not EJEMPLO.exists()):
        procesar("factura_de_ejemplo.pdf", EJEMPLO.read_bytes())

    for factura in st.session_state.get("procesadas", []):
        with st.container(border=True):
            formulario(factura)

with tab_historial:
    c1, c2, c3 = st.columns(3)
    emisor = c1.text_input("Emisor o NIF")
    desde = c2.date_input("Desde", value=None, format="DD/MM/YYYY")
    hasta = c3.date_input("Hasta", value=None, format="DD/MM/YYYY")
    params = {"size": 100, "emisor": emisor or None,
              "desde": desde.isoformat() if desde else None,
              "hasta": hasta.isoformat() if hasta else None}
    r = api("GET", "/facturas", params={k: v for k, v in params.items() if v})
    if r is not None:
        data = r.json()
        st.write(f"{data['total']} facturas")
        st.dataframe(
            [
                {
                    "ID": f["id"], "Número": f["datos"]["numero"],
                    "Fecha": f["datos"]["fecha_emision"], "Emisor": f["datos"]["emisor"]["nombre"],
                    "Total (€)": f["datos"]["total"], "Estado": f["estado"],
                    "Avisos": len(f["avisos"]),
                }
                for f in data["items"]
            ],
            use_container_width=True, hide_index=True,
        )
    excel = api("GET", "/facturas/export.xlsx")
    if excel is not None:
        st.download_button("Descargar Excel", excel.content, file_name="facturas.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
