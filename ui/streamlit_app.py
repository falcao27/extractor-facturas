"""Interface de demonstração: enviar faturas, ver como são processadas, revisar e exportar."""

import os
import time
from datetime import date
from pathlib import Path

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
EXEMPLOS = Path(__file__).resolve().parents[1] / "ejemplos"
EXEMPLO = EXEMPLOS / "factura_prueba_con_errores.pdf"
NOMES_EXEMPLOS = {
    "factura_prueba_correcta.pdf": "Fatura de teste correta",
    "factura_prueba_con_errores.pdf": "Fatura de teste com erros",
}
TIMEOUT = httpx.Timeout(120.0, connect=10.0)
ICONE_ETAPA = {"ok": "✅", "aviso": "⚠️", "error": "❌"}
STATUS = {
    "procesada": ("green", "Processada"),
    "con_avisos": ("orange", "Com avisos"),
    "revisada": ("blue", "Revisada"),
    "error": ("red", "Erro"),
}

st.set_page_config(page_title="Extrator de faturas com IA", page_icon="🧾", layout="wide")


def eur(valor: float | None) -> str:
    inteiro, dec = f"{valor or 0:,.2f}".split(".")
    return f"{inteiro.replace(',', '.')},{dec} €"


def api(method: str, path: str, **kwargs) -> httpx.Response | None:
    try:
        r = httpx.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)
    except httpx.HTTPError:
        st.error("Não foi possível conectar à API. Na demo gratuita ela pode levar ~1 minuto "
                 "para acordar: tente de novo.")
        return None
    if r.status_code >= 400:
        e_json = "json" in r.headers.get("content-type", "")
        st.error(f"Erro {r.status_code}: {r.json().get('detail', r.text) if e_json else r.text}")
        return None
    return r


def processar(nome: str, conteudo: bytes) -> None:
    with st.spinner(f"Processando {nome}..."):
        r = api("POST", "/facturas", files={"archivo": (nome, conteudo, "application/pdf")})
    if r is not None:
        fatura = r.json()
        st.session_state.setdefault("processadas", []).insert(0, fatura)
        st.session_state.setdefault("para_animar", set()).add(fatura["id"])


def mostrar_etapas(fatura: dict) -> None:
    """Linha do tempo do que o sistema fez com o PDF."""
    etapas = fatura.get("pasos") or []
    if not etapas:
        return
    animar = fatura["id"] in st.session_state.get("para_animar", set())
    total_ms = sum(e["ms"] for e in etapas)
    conclusao = {
        "procesada": "tudo correto",
        "con_avisos": "precisa de revisão",
        "revisada": "revisada e confirmada pelo usuário",
    }.get(fatura["estado"], fatura["estado"])

    with st.status("Processando a fatura...", expanded=True) as status:
        for i, etapa in enumerate(etapas, start=1):
            if animar:
                time.sleep(0.4)
            st.markdown(
                f"{ICONE_ETAPA.get(etapa['estado'], '•')} **{i}. {etapa['nombre']}** "
                f"<span style='color:gray'>· {etapa['ms']} ms</span><br>"
                f"<span style='color:gray;font-size:0.9em'>{etapa['detalle']}</span>",
                unsafe_allow_html=True,
            )
        status.update(
            label=f"Processada em {total_ms / 1000:.2f} s · {conclusao}",
            state="complete",
            expanded=True,
        )
    st.session_state.get("para_animar", set()).discard(fatura["id"])


def mostrar_resultado(fatura: dict) -> None:
    d = fatura["datos"]
    cor, texto = STATUS.get(fatura["estado"], ("gray", fatura["estado"]))
    st.markdown(f"### Resultado · :{cor}-background[{texto}]")

    c1, c2, c3, c4, c5 = st.columns(5)
    data = date.fromisoformat(d["fecha_emision"]).strftime("%d/%m/%Y")
    c1.markdown(f"<small style='color:gray'>Fatura · {data}</small><br>"
                f"<span style='font-size:1.25em;font-weight:600'>{d['numero']}</span>",
                unsafe_allow_html=True)
    c2.metric("Base tributável", eur(d["base_imponible"]))
    c3.metric(f"IVA {d['tipo_iva']:g} %", eur(d["cuota_iva"]))
    c4.metric("Retenção IRPF", eur(d["retencion_irpf"]) if d["retencion_irpf"] else "—")
    c5.metric("Total a pagar", eur(d["total"]))

    c1, c2 = st.columns(2)
    c1.markdown(f"**Emissor**  \n{d['emisor']['nombre']}  \n`{d['emisor']['nif']}`")
    c2.markdown(f"**Destinatário**  \n{d['receptor']['nombre']}  \n`{d['receptor']['nif']}`")

    st.dataframe(
        [
            {"Descrição": linha["descripcion"], "Quantidade": linha["cantidad"],
             "Preço unitário": eur(linha["precio_unitario"]), "Valor": eur(linha["importe"])}
            for linha in d["lineas"]
        ],
        use_container_width=True, hide_index=True,
    )

    regras = fatura.get("reglas") or []
    if regras:
        corretas = sum(r["ok"] for r in regras)
        st.markdown(f"**Validações: {corretas} de {len(regras)} corretas**")
        cols = st.columns(2)
        for i, regra in enumerate(regras):
            with cols[i % 2]:
                if regra["ok"]:
                    st.markdown(f"✅ {regra['nombre']}")
                else:
                    st.warning(f"**{regra['nombre']}**  \n{regra['detalle']}", icon="⚠️")

    st.caption(
        f"{fatura['archivo']} · modelo {fatura['modelo']} · "
        f"{fatura['tokens_entrada'] + fatura['tokens_salida']} tokens · "
        f"custo {fatura['coste_eur']:.5f} € · {fatura['tiempo_ms']} ms"
        + (" · escaneada" if fatura["escaneada"] else "")
    )


def formulario(fatura: dict) -> None:
    d = fatura["datos"]
    fid = fatura["id"]
    with st.form(f"form_{fid}"):
        c1, c2 = st.columns(2)
        numero = c1.text_input("Número", d["numero"], key=f"num_{fid}")
        data = c2.date_input("Data de emissão", date.fromisoformat(d["fecha_emision"]),
                             format="DD/MM/YYYY", key=f"data_{fid}")
        c1, c2 = st.columns(2)
        emissor_nome = c1.text_input("Emissor", d["emisor"]["nombre"], key=f"en_{fid}")
        emissor_nif = c2.text_input("NIF emissor", d["emisor"]["nif"], key=f"enif_{fid}")
        c1, c2 = st.columns(2)
        dest_nome = c1.text_input("Destinatário", d["receptor"]["nombre"], key=f"dn_{fid}")
        dest_nif = c2.text_input("NIF destinatário", d["receptor"]["nif"], key=f"dnif_{fid}")

        linhas = st.data_editor(
            d["lineas"], num_rows="dynamic", use_container_width=True, key=f"linhas_{fid}",
            column_config={
                "descripcion": st.column_config.TextColumn("Descrição", width="large"),
                "cantidad": st.column_config.NumberColumn("Quantidade"),
                "precio_unitario": st.column_config.NumberColumn("Preço unitário",
                                                                 format="%.2f €"),
                "importe": st.column_config.NumberColumn("Valor", format="%.2f €"),
            },
        )

        aliquotas = [21.0, 10.0, 4.0, 0.0]
        c1, c2, c3, c4, c5 = st.columns(5)
        base = c1.number_input("Base tributável", value=d["base_imponible"], format="%.2f",
                               key=f"base_{fid}")
        aliquota = c2.selectbox(
            "Alíquota IVA %", aliquotas,
            index=aliquotas.index(d["tipo_iva"]) if d["tipo_iva"] in aliquotas else 0,
            key=f"aliq_{fid}",
        )
        iva = c3.number_input("Valor IVA", value=d["cuota_iva"], format="%.2f",
                              key=f"iva_{fid}")
        irpf = c4.number_input("Retenção IRPF", value=d["retencion_irpf"] or 0.0,
                               format="%.2f", key=f"irpf_{fid}")
        total = c5.number_input("Total", value=d["total"], format="%.2f", key=f"total_{fid}")

        c1, c2 = st.columns(2)
        salvar = c1.form_submit_button("Salvar correção (revalida)")
        confirmar = c2.form_submit_button("Confirmar fatura ✅", type="primary")

    if salvar or confirmar:
        mudancas = {
            "numero": numero,
            "fecha_emision": data.isoformat(),
            "emisor": {"nombre": emissor_nome, "nif": emissor_nif},
            "receptor": {"nombre": dest_nome, "nif": dest_nif},
            "lineas": [linha for linha in linhas if linha.get("descripcion")],
            "base_imponible": base,
            "tipo_iva": aliquota,
            "cuota_iva": iva,
            "retencion_irpf": irpf or None,
            "total": total,
            "confirmar": confirmar,
        }
        r = api("PATCH", f"/facturas/{fid}", json=mudancas)
        if r is not None:
            nova = r.json()
            corretas = sum(regra["ok"] for regra in nova["reglas"])
            revisao = {
                "nombre": "Revisão manual",
                "estado": "ok" if not nova["avisos"] else "aviso",
                "ms": 0,
                "detalle": f"{'Confirmada' if confirmar else 'Corrigida'} pelo usuário · "
                f"revalidada: {corretas} de {len(nova['reglas'])} regras corretas",
            }
            nova["pasos"] = fatura.get("pasos", []) + [revisao]
            processadas = st.session_state["processadas"]
            processadas[:] = [nova if f["id"] == fid else f for f in processadas]
            st.toast("Fatura confirmada" if confirmar else "Correção salva e revalidada")
            st.rerun()


with st.sidebar:
    st.header("🧪 Faturas de teste")
    st.caption("Baixe e envie, ou use o botão de exemplo.")
    for pdf in sorted(EXEMPLOS.glob("*.pdf")):
        st.download_button(NOMES_EXEMPLOS.get(pdf.name, pdf.stem), pdf.read_bytes(),
                           file_name=pdf.name, mime="application/pdf",
                           use_container_width=True)

st.title("🧾 Extrator de faturas com IA")
st.caption(
    "Envie faturas espanholas em PDF: os dados são extraídos, o NIF/CIF, o IVA, o IRPF e os "
    "totais são validados, e você pode corrigir e baixar tudo em Excel. Os PDFs não são "
    "armazenados."
)

saude = api("GET", "/health")
if saude is not None and saude.json().get("llm_provider") == "demo":
    st.info(
        "**Modo demo (sem LLM, sem custo):** são reconhecidas as faturas de teste e as 30 de "
        "`eval/dataset`. Validações, avisos, correções e Excel funcionam igual ao modo com "
        "Claude.",
        icon="🧪",
    )

aba_enviar, aba_historico = st.tabs(["Enviar faturas", "Histórico"])

with aba_enviar:
    # Trocar a key esvazia o seletor depois de processar, para não repetir arquivos
    st.session_state.setdefault("uploader", 0)
    arquivos = st.file_uploader("PDFs de faturas (máx. 5 MB cada)", type=["pdf"],
                                accept_multiple_files=True,
                                key=f"uploader_{st.session_state['uploader']}")
    c1, c2, _ = st.columns([1, 1.3, 3])
    if c1.button("Processar", type="primary", disabled=not arquivos):
        for arquivo in arquivos:
            processar(arquivo.name, arquivo.getvalue())
        st.session_state["uploader"] += 1
        st.rerun()
    if c2.button("Testar com fatura de exemplo", disabled=not EXEMPLO.exists()):
        processar(EXEMPLO.name, EXEMPLO.read_bytes())

    for fatura in st.session_state.get("processadas", []):
        with st.container(border=True):
            mostrar_etapas(fatura)
            mostrar_resultado(fatura)
            with st.expander("✏️ Revisar e corrigir", expanded=bool(fatura["avisos"])):
                formulario(fatura)

with aba_historico:
    c1, c2, c3 = st.columns(3)
    emissor = c1.text_input("Emissor ou NIF")
    desde = c2.date_input("De", value=None, format="DD/MM/YYYY")
    ate = c3.date_input("Até", value=None, format="DD/MM/YYYY")
    params = {"size": 100, "emisor": emissor or None,
              "desde": desde.isoformat() if desde else None,
              "hasta": ate.isoformat() if ate else None}
    r = api("GET", "/facturas", params={k: v for k, v in params.items() if v})
    if r is not None:
        dados = r.json()
        st.write(f"{dados['total']} faturas")
        st.dataframe(
            [
                {
                    "ID": f["id"], "Número": f["datos"]["numero"],
                    "Data": f["datos"]["fecha_emision"],
                    "Emissor": f["datos"]["emisor"]["nombre"],
                    "Total": eur(f["datos"]["total"]),
                    "Status": STATUS.get(f["estado"], ("", f["estado"]))[1],
                    "Avisos": len(f["avisos"]),
                }
                for f in dados["items"]
            ],
            use_container_width=True, hide_index=True,
        )
    excel = api("GET", "/facturas/export.xlsx")
    if excel is not None:
        st.download_button("Baixar Excel", excel.content, file_name="faturas.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
