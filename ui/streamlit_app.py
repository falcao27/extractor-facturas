"""Interfaz de demo: subir facturas, ver cómo se procesan, revisar avisos, corregir y exportar."""

import os
import time
from datetime import date
from pathlib import Path

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
EJEMPLOS = Path(__file__).resolve().parents[1] / "ejemplos"
EJEMPLO = EJEMPLOS / "factura_prueba_con_errores.pdf"
TIMEOUT = httpx.Timeout(120.0, connect=10.0)
ICONO_PASO = {"ok": "✅", "aviso": "⚠️", "error": "❌"}
ESTADOS = {
    "procesada": ("green", "Procesada"),
    "con_avisos": ("orange", "Con avisos"),
    "revisada": ("blue", "Revisada"),
    "error": ("red", "Error"),
}

st.set_page_config(page_title="Extractor de facturas con IA", page_icon="🧾", layout="wide")


def eur(valor: float | None) -> str:
    entero, dec = f"{valor or 0:,.2f}".split(".")
    return f"{entero.replace(',', '.')},{dec} €"


def api(method: str, path: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError:
        st.error("No se pudo conectar con la API. Si es la demo gratuita, puede tardar "
                 "~1 minuto en despertar: inténtalo de nuevo.")
        return None
    if r.status_code >= 400:
        es_json = "json" in r.headers.get("content-type", "")
        st.error(f"Error {r.status_code}: {r.json().get('detail', r.text) if es_json else r.text}")
        return None
    return r


def procesar(nombre: str, contenido: bytes) -> None:
    with st.spinner(f"Procesando {nombre}..."):
        r = api("POST", "/facturas", files={"archivo": (nombre, contenido, "application/pdf")})
    if r is not None:
        factura = r.json()
        st.session_state.setdefault("procesadas", []).insert(0, factura)
        st.session_state.setdefault("por_animar", set()).add(factura["id"])


def mostrar_pasos(factura: dict) -> None:
    """Línea de tiempo de lo que hizo el sistema con el PDF."""
    pasos = factura.get("pasos") or []
    if not pasos:
        return
    animar = factura["id"] in st.session_state.get("por_animar", set())
    total_ms = sum(p["ms"] for p in pasos)
    conclusion = {
        "procesada": "todo correcto",
        "con_avisos": "requiere revisión",
        "revisada": "revisada y confirmada por el usuario",
    }.get(factura["estado"], factura["estado"])

    with st.status("Procesando la factura...", expanded=True) as estado:
        for i, paso in enumerate(pasos, start=1):
            if animar:
                time.sleep(0.4)
            st.markdown(
                f"{ICONO_PASO.get(paso['estado'], '•')} **{i}. {paso['nombre']}** "
                f"<span style='color:gray'>· {paso['ms']} ms</span><br>"
                f"<span style='color:gray;font-size:0.9em'>{paso['detalle']}</span>",
                unsafe_allow_html=True,
            )
        estado.update(
            label=f"Procesada en {total_ms / 1000:.2f} s · {conclusion}",
            state="complete",
            expanded=True,
        )
    st.session_state.get("por_animar", set()).discard(factura["id"])


def mostrar_resultado(factura: dict) -> None:
    d = factura["datos"]
    color, texto = ESTADOS.get(factura["estado"], ("gray", factura["estado"]))
    st.markdown(f"### Resultado · :{color}-background[{texto}]")

    c1, c2, c3, c4, c5 = st.columns(5)
    fecha = date.fromisoformat(d["fecha_emision"]).strftime("%d/%m/%Y")
    c1.markdown(f"<small style='color:gray'>Factura · {fecha}</small><br>"
                f"<span style='font-size:1.25em;font-weight:600'>{d['numero']}</span>",
                unsafe_allow_html=True)
    c2.metric("Base imponible", eur(d["base_imponible"]))
    c3.metric(f"IVA {d['tipo_iva']:g} %", eur(d["cuota_iva"]))
    c4.metric("Retención IRPF", eur(d["retencion_irpf"]) if d["retencion_irpf"] else "—")
    c5.metric("Total a pagar", eur(d["total"]))

    c1, c2 = st.columns(2)
    c1.markdown(f"**Emisor**  \n{d['emisor']['nombre']}  \n`{d['emisor']['nif']}`")
    c2.markdown(f"**Receptor**  \n{d['receptor']['nombre']}  \n`{d['receptor']['nif']}`")

    st.dataframe(
        [
            {"Descripción": linea["descripcion"], "Cantidad": linea["cantidad"],
             "Precio unitario": eur(linea["precio_unitario"]), "Importe": eur(linea["importe"])}
            for linea in d["lineas"]
        ],
        use_container_width=True, hide_index=True,
    )

    reglas = factura.get("reglas") or []
    if reglas:
        correctas = sum(r["ok"] for r in reglas)
        st.markdown(f"**Validaciones: {correctas} de {len(reglas)} correctas**")
        cols = st.columns(2)
        for i, regla in enumerate(reglas):
            with cols[i % 2]:
                if regla["ok"]:
                    st.markdown(f"✅ {regla['nombre']}")
                else:
                    st.warning(f"**{regla['nombre']}**  \n{regla['detalle']}", icon="⚠️")

    st.caption(
        f"{factura['archivo']} · modelo {factura['modelo']} · "
        f"{factura['tokens_entrada'] + factura['tokens_salida']} tokens · "
        f"coste {factura['coste_eur']:.5f} € · {factura['tiempo_ms']} ms"
        + (" · escaneada" if factura["escaneada"] else "")
    )


def formulario(factura: dict) -> None:
    d = factura["datos"]
    fid = factura["id"]
    with st.form(f"form_{fid}"):
        c1, c2 = st.columns(2)
        numero = c1.text_input("Número", d["numero"], key=f"num_{fid}")
        fecha = c2.date_input("Fecha de emisión", date.fromisoformat(d["fecha_emision"]),
                              format="DD/MM/YYYY", key=f"fecha_{fid}")
        c1, c2 = st.columns(2)
        emisor_nombre = c1.text_input("Emisor", d["emisor"]["nombre"], key=f"en_{fid}")
        emisor_nif = c2.text_input("NIF emisor", d["emisor"]["nif"], key=f"enif_{fid}")
        c1, c2 = st.columns(2)
        receptor_nombre = c1.text_input("Receptor", d["receptor"]["nombre"], key=f"rn_{fid}")
        receptor_nif = c2.text_input("NIF receptor", d["receptor"]["nif"], key=f"rnif_{fid}")

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

        tipos = [21.0, 10.0, 4.0, 0.0]
        c1, c2, c3, c4, c5 = st.columns(5)
        base = c1.number_input("Base imponible", value=d["base_imponible"], format="%.2f",
                               key=f"base_{fid}")
        tipo = c2.selectbox("Tipo IVA %", tipos,
                            index=tipos.index(d["tipo_iva"]) if d["tipo_iva"] in tipos else 0,
                            key=f"tipo_{fid}")
        cuota = c3.number_input("Cuota IVA", value=d["cuota_iva"], format="%.2f",
                                key=f"cuota_{fid}")
        irpf = c4.number_input("Retención IRPF", value=d["retencion_irpf"] or 0.0,
                               format="%.2f", key=f"irpf_{fid}")
        total = c5.number_input("Total", value=d["total"], format="%.2f", key=f"total_{fid}")

        c1, c2 = st.columns(2)
        guardar = c1.form_submit_button("Guardar corrección (revalida)")
        confirmar = c2.form_submit_button("Confirmar factura ✅", type="primary")

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
            nueva = r.json()
            correctas = sum(regla["ok"] for regla in nueva["reglas"])
            revision = {
                "nombre": "Revisión manual",
                "estado": "ok" if not nueva["avisos"] else "aviso",
                "ms": 0,
                "detalle": f"{'Confirmada' if confirmar else 'Corregida'} por el usuario · "
                f"revalidada: {correctas} de {len(nueva['reglas'])} reglas correctas",
            }
            nueva["pasos"] = factura.get("pasos", []) + [revision]
            procesadas = st.session_state["procesadas"]
            procesadas[:] = [nueva if f["id"] == fid else f for f in procesadas]
            st.toast("Factura confirmada" if confirmar else "Corrección guardada y revalidada")
            st.rerun()


with st.sidebar:
    st.header("🧪 Facturas de prueba")
    st.caption("Descárgalas y súbelas, o usa el botón de ejemplo.")
    for pdf in sorted(EJEMPLOS.glob("*.pdf")):
        st.download_button(pdf.stem.replace("_", " ").capitalize(), pdf.read_bytes(),
                           file_name=pdf.name, mime="application/pdf",
                           use_container_width=True)

st.title("🧾 Extractor de facturas con IA")
st.caption(
    "Sube facturas españolas en PDF: se extraen los datos, se validan NIF/CIF, IVA, IRPF y "
    "totales, y puedes corregirlas y descargarlas en Excel. Los PDF no se guardan."
)

salud = api("GET", "/health")
if salud is not None and salud.json().get("llm_provider") == "demo":
    st.info(
        "**Modo demo (sin LLM, sin coste):** se reconocen las facturas de prueba y las 30 de "
        "`eval/dataset`. Validaciones, avisos, correcciones y Excel funcionan igual que con "
        "Claude.",
        icon="🧪",
    )

tab_subir, tab_historial = st.tabs(["Subir facturas", "Historial"])

with tab_subir:
    # Cambiar la key vacía el selector tras procesar, para no repetir archivos
    st.session_state.setdefault("uploader", 0)
    archivos = st.file_uploader("PDF de facturas (máx. 5 MB cada uno)", type=["pdf"],
                                accept_multiple_files=True,
                                key=f"uploader_{st.session_state['uploader']}")
    c1, c2, _ = st.columns([1, 1.3, 3])
    if c1.button("Procesar", type="primary", disabled=not archivos):
        for archivo in archivos:
            procesar(archivo.name, archivo.getvalue())
        st.session_state["uploader"] += 1
        st.rerun()
    if c2.button("Probar con factura de ejemplo", disabled=not EJEMPLO.exists()):
        procesar(EJEMPLO.name, EJEMPLO.read_bytes())

    for factura in st.session_state.get("procesadas", []):
        with st.container(border=True):
            mostrar_pasos(factura)
            mostrar_resultado(factura)
            with st.expander("✏️ Revisar y corregir", expanded=bool(factura["avisos"])):
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
                    "Total": eur(f["datos"]["total"]),
                    "Estado": ESTADOS.get(f["estado"], ("", f["estado"]))[1],
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
