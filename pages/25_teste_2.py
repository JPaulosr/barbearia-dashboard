# -*- coding: utf-8 -*-
# Detalhes do Funcionário — versão mobile-first (tabs, CSS compacto)
import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

# =========================
# CONFIG GERAL + CSS MOBILE
# =========================
st.set_page_config(page_title="Detalhes do Funcionário", layout="wide")

st.markdown("""
<style>
/* reduz margens no mobile */
.block-container { padding-top: 0.6rem; padding-left: 0.6rem; padding-right: 0.6rem; }

/* títulos um pouco menores no mobile */
h1, h2, h3 { line-height: 1.2; }

/* botões maiores para toque */
.stButton>button, .stDownloadButton>button {
  padding: 0.8rem 1rem; border-radius: 12px; font-size: 1rem;
}

/* cards de métricas com sombra suave */
div[data-testid="stMetric"] {
  border-radius: 14px; box-shadow: 0 6px 18px rgba(0,0,0,.08);
  padding: 0.6rem; background: rgba(250,250,250,.75);
}

/* tabelas com rolagem horizontal no mobile */
[data-testid="stDataFrame"] div[role="table"] { overflow-x: auto; }

/* esconde header quando instalado como app (webclip/pwa) */
@media (display-mode: standalone) { header, footer { display:none; } }
</style>
""", unsafe_allow_html=True)

st.title("🧑‍💼 Detalhes do Funcionário")

# =========================
# CONFIGURAÇÃO GOOGLE SHEETS
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]

    # datas
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)

    # numéricos
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    else:
        df["Valor"] = 0.0

    # normaliza coluna de pagamento (fiado/pago)
    conta_col = "Conta" if "Conta" in df.columns else ("Forma de Pagamento" if "Forma de Pagamento" in df.columns else None)
    if conta_col:
        df["Conta_norm"] = df[conta_col].astype(str).str.strip().str.lower().replace({"nan": ""})
    else:
        df["Conta_norm"] = ""

    # garante colunas esperadas
    for c in ["Funcionário", "Cliente", "Serviço"]:
        if c not in df.columns:
            df[c] = ""

    return df

@st.cache_data
def carregar_despesas():
    planilha = conectar_sheets()
    aba_desp = planilha.worksheet("Despesas")
    df_desp = get_as_dataframe(aba_desp).dropna(how="all")
    df_desp.columns = [str(col).strip() for col in df_desp.columns]
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year.astype(int)

    # numérico
    if "Valor" in df_desp.columns:
        df_desp["Valor"] = pd.to_numeric(df_desp["Valor"], errors="coerce").fillna(0.0)
    else:
        df_desp["Valor"] = 0.0

    # normaliza texto
    for c in ["Prestador", "Descrição"]:
        if c not in df_desp.columns:
            df_desp[c] = ""
        else:
            df_desp[c] = df_desp[c].astype(str)

    return df_desp

def fmt_brl(x: float) -> str:
    return f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

# =========================
# CARGA
# =========================
df = carregar_dados()
df_despesas = carregar_despesas()

# =========================
# FILTROS SUPERIORES (compactos)
# =========================
funcionarios = sorted(df["Funcionário"].dropna().unique().tolist())
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)

col_top = st.columns(2)
ano_escolhido = col_top[0].selectbox("🗕️ Ano", anos, index=0)
funcionario_escolhido = col_top[1].selectbox("📋 Funcionário", funcionarios)

modo_pag = st.radio(
    "Filtro de pagamento",
    ["Apenas pagos", "Apenas fiado", "Incluir tudo"],
    index=0, horizontal=True,
    help="Considera a coluna Conta/Forma de Pagamento normalizada."
)

df_base_ano = df[df["Ano"] == ano_escolhido].copy()
if modo_pag == "Apenas pagos":
    df_base_ano = df_base_ano[df_base_ano["Conta_norm"] != "fiado"]
elif modo_pag == "Apenas fiado":
    df_base_ano = df_base_ano[df_base_ano["Conta_norm"] == "fiado"]

df_func = df_base_ano[df_base_ano["Funcionário"] == funcionario_escolhido].copy()

with st.expander("🔎 Filtros avançados", expanded=False):
    col_f1, col_f2, col_f3 = st.columns(3)
    # Mês
    meses_disponiveis = sorted(df_func["Data"].dt.month.unique())
    mes_filtro = col_f1.selectbox("📆 Mês", options=["Todos"] + list(meses_disponiveis))
    if mes_filtro != "Todos":
        df_func = df_func[df_func["Data"].dt.month == mes_filtro]

    # Dia
    dias_disponiveis = sorted(df_func["Data"].dt.day.unique())
    dia_filtro = col_f2.selectbox("📅 Dia", options=["Todos"] + list(dias_disponiveis))
    if dia_filtro != "Todos":
        df_func = df_func[df_func["Data"].dt.day == dia_filtro]

    # Semana ISO
    df_func["Semana"] = df_func["Data"].dt.isocalendar().week
    semanas_disponiveis = sorted(df_func["Semana"].unique().tolist())
    semana_filtro = col_f3.selectbox("🗓️ Semana ISO", options=["Todas"] + list(semanas_disponiveis))
    if semana_filtro != "Todas":
        df_func = df_func[df_func["Semana"] == semana_filtro]

    # Tipo de serviço
    tipos_servico = sorted(df_func["Serviço"].dropna().unique().tolist())
    tipo_selecionado = st.multiselect("Tipo de serviço", tipos_servico)
    if tipo_selecionado:
        df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# =========================
# TABS (mobile-first)
# =========================
tab_resumo, tab_graficos, tab_historico, tab_exportar = st.tabs(
    ["📌 Resumo", "📊 Gráficos", "📜 Histórico", "📄 Exportar"]
)

# ======= TAB RESUMO =======
with tab_resumo:
    st.subheader("📌 Insights do Funcionário")

    # Métricas (2 por linha no mobile fica ok)
    col1, col2 = st.columns(2)
    col3, col4 = st.columns(2)

    total_atendimentos = int(df_func.shape[0])
    clientes_unicos = int(df_func["Cliente"].nunique())
    total_receita = float(df_func["Valor"].sum())
    ticket_medio_geral = float(df_func["Valor"].mean()) if total_atendimentos > 0 else 0.0

    col1.metric("🔢 Atendimentos", total_atendimentos)
    col2.metric("👥 Clientes únicos", clientes_unicos)
    col3.metric("💰 Receita total", fmt_brl(total_receita))
    col4.metric("🎫 Ticket médio", fmt_brl(ticket_medio_geral))

    # Dia mais cheio
    dia_mais_cheio = (
        df_func.groupby(df_func["Data"].dt.date).size()
        .reset_index(name="Atendimentos")
        .sort_values("Atendimentos", ascending=False)
        .head(1)
    )
    if not dia_mais_cheio.empty:
        data_cheia = pd.to_datetime(dia_mais_cheio.iloc[0, 0]).strftime("%d/%m/%Y")
        qtd_atend = int(dia_mais_cheio.iloc[0, 1])
        st.info(f"📅 Dia com mais atendimentos: **{data_cheia}** com **{qtd_atend}**")

    # Resumos de receita/comissão (tabelas curtas)
    if funcionario_escolhido.lower() == "vinicius":
        bruto = float(df_func["Valor"].sum())
        comissao_real = float(
            df_despesas[
                (df_despesas["Prestador"] == "Vinicius") &
                (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
                (df_despesas["Ano"] == ano_escolhido)
            ]["Valor"].abs().sum()
        )
        receita_liquida = comissao_real
        receita_salao = bruto - comissao_real

        st.markdown("#### 💸 Receita do Vinicius & Salão")
        st.dataframe(
            pd.DataFrame({
                "Tipo de Receita": [
                    "Receita Bruta de Vinicius",
                    "Receita de Vinicius (comissão real)",
                    "Valor que ficou para o salão"
                ],
                "Valor": [fmt_brl(bruto), fmt_brl(receita_liquida), fmt_brl(receita_salao)]
            }),
            use_container_width=True, height=160
        )

    elif funcionario_escolhido.lower() == "jpaulo":
        receita_jpaulo = float(df_func["Valor"].sum())
        receita_vinicius_total = float(
            df_base_ano[(df_base_ano["Funcionário"] == "Vinicius") & (df_base_ano["Ano"] == ano_escolhido)]["Valor"].sum()
        )
        comissao_paga = float(
            df_despesas[
                (df_despesas["Prestador"] == "Vinicius") &
                (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
                (df_despesas["Ano"] == ano_escolhido)
            ]["Valor"].abs().sum()
        )
        receita_liquida_vinicius = max(0.0, receita_vinicius_total - comissao_paga)
        receita_total_salao = receita_jpaulo + receita_liquida_vinicius

        st.markdown("#### 💰 Receita do Salão (JPaulo como dono)")
        st.dataframe(
            pd.DataFrame({
                "Origem": [
                    "Receita JPaulo",
                    "Receita Vinicius (líquida)",
                    "Comissão paga ao Vinicius (despesa)",
                    "Total receita do salão"
                ],
                "Valor": [fmt_brl(receita_jpaulo), fmt_brl(receita_liquida_vinicius), fmt_brl(comissao_paga), fmt_brl(receita_total_salao)]
            }),
            use_container_width=True, height=180
        )

# ======= TAB GRÁFICOS =======
with tab_graficos:
    # Atendimentos por dia da semana
    st.markdown("### 📆 Atendimentos por dia da semana")
    dias_semana = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
    order_semana = {"Seg":0, "Ter":1, "Qua":2, "Qui":3, "Sex":4, "Sáb":5, "Dom":6}

    df_semana = df_func.copy()
    df_semana["DiaSemana"] = df_semana["Data"].dt.dayofweek.map(dias_semana)
    grafico_semana = (
        df_semana.groupby("DiaSemana").size()
        .reset_index(name="Qtd Atendimentos")
        .sort_values("DiaSemana", key=lambda x: x.map(order_semana))
    )
    fig_dias = px.bar(
        grafico_semana, x="DiaSemana", y="Qtd Atendimentos",
        text_auto=True, template="plotly_white"
    )
    fig_dias.update_layout(height=380, margin=dict(t=30, b=20))
    st.plotly_chart(fig_dias, use_container_width=True, key="graf_semana")

    # Média de atendimentos por dia do mês
    st.markdown("### 🗓️ Média de atendimentos por dia do mês")
    df_dm = df_func.copy()
    df_dm["Dia"] = df_dm["Data"].dt.day
    media_por_dia = df_dm.groupby("Dia").size().reset_index(name="Média por dia")
    fig_dia_mes = px.line(media_por_dia, x="Dia", y="Média por dia", markers=True, template="plotly_white")
    fig_dia_mes.update_layout(height=360, margin=dict(t=30, b=20))
    st.plotly_chart(fig_dia_mes, use_container_width=True, key="graf_media_dia")

    # Receita mensal (com lógica especial p/ JPaulo)
    st.markdown("### 📊 Receita Mensal")
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
        7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df_mensal = df_func.copy()
    df_mensal["MesNum"] = df_mensal["Data"].dt.month
    df_mensal["MesNome"] = df_mensal["MesNum"].map(meses_pt) + df_mensal["Data"].dt.strftime(" %Y")
    receita_jp = df_mensal.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
    receita_jp = receita_jp.sort_values("MesNum")

    # Comissão real Vinicius (sempre por ano escolhido)
    df_com_vinicius = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
        (df_despesas["Ano"] == ano_escolhido)
    ].copy()
    df_com_vinicius["Valor"] = df_com_vinicius["Valor"].abs()
    df_com_vinicius["MesNum"] = df_com_vinicius["Data"].dt.month
    df_com_vinicius = df_com_vinicius.groupby("MesNum")["Valor"].sum().reset_index(name="ComissaoRealVinicius")

    if funcionario_escolhido.lower() == "jpaulo":
        receita_mes_vinicius = df_base_ano[
            (df_base_ano["Funcionário"] == "Vinicius") & (df_base_ano["Ano"] == ano_escolhido)
        ].copy()
        receita_mes_vinicius["MesNum"] = receita_mes_vinicius["Data"].dt.month
        receita_mes_vinicius = receita_mes_vinicius.groupby("MesNum")["Valor"].sum().reset_index(name="ReceitaVinicius")

        receita_merged = receita_jp.merge(df_com_vinicius, on="MesNum", how="left").merge(
            receita_mes_vinicius, on="MesNum", how="left"
        ).fillna(0)

        receita_merged["LiquidoVinicius"] = (receita_merged["ReceitaVinicius"] - receita_merged["ComissaoRealVinicius"]).clip(lower=0)
        receita_merged["ReceitaRealSalao"] = receita_merged["JPaulo"] + receita_merged["LiquidoVinicius"]

        receita_melt = receita_merged.melt(
            id_vars=["MesNum", "MesNome"],
            value_vars=["JPaulo", "ReceitaRealSalao"],
            var_name="Tipo", value_name="Valor"
        ).sort_values("MesNum")

        fig_mensal_comp = px.bar(
            receita_melt, x="MesNome", y="Valor", color="Tipo",
            barmode="group", text_auto=True,
            labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""}
        )
        fig_mensal_comp.update_layout(height=420, template="plotly_white", margin=dict(t=30, b=20))
        st.plotly_chart(fig_mensal_comp, use_container_width=True, key="graf_mensal_comp")

        # Tabela curta
        tabela = receita_merged[["MesNome", "JPaulo", "ComissaoRealVinicius", "ReceitaRealSalao"]].copy()
        tabela["Receita JPaulo"] = tabela["JPaulo"].apply(fmt_brl)
        tabela["Comissão paga ao Vinicius"] = tabela["ComissaoRealVinicius"].apply(fmt_brl)
        tabela["Receita Real do Salão"] = tabela["ReceitaRealSalao"].apply(fmt_brl)
        st.dataframe(
            tabela[["MesNome", "Receita JPaulo", "Comissão paga ao Vinicius", "Receita Real do Salão"]],
            use_container_width=True, height=220
        )

    else:
        receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(fmt_brl)
        fig_mensal = px.bar(
            receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
            labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"}
        )
        fig_mensal.update_layout(height=420, template="plotly_white", margin=dict(t=30, b=20))
        fig_mensal.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_mensal, use_container_width=True, key="graf_mensal_simples")

    # Ticket Médio por mês (com regra 11/05)
    st.markdown("### 📉 Ticket Médio por Mês")
    df_tk = df_func.copy()
    data_referencia = pd.to_datetime("2025-05-11")
    df_tk["Grupo"] = df_tk["Data"].dt.strftime("%Y-%m-%d") + "_" + df_tk["Cliente"]

    antes_ticket = df_tk[df_tk["Data"] < data_referencia].copy()
    antes_ticket["AnoMes"] = antes_ticket["Data"].dt.to_period("M").astype(str)
    antes_ticket = antes_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

    depois_ticket = df_tk[df_tk["Data"] >= data_referencia].copy()
    depois_ticket = depois_ticket.groupby(["Grupo", "Data"])["Valor"].sum().reset_index()
    depois_ticket["AnoMes"] = depois_ticket["Data"].dt.to_period("M").astype(str)
    depois_ticket = depois_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

    ticket_mensal = pd.concat([antes_ticket, depois_ticket]).groupby("AnoMes")["Ticket Médio"].mean().reset_index()
    ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(fmt_brl)
    st.dataframe(ticket_mensal, use_container_width=True, height=240)

# ======= TAB HISTÓRICO =======
with tab_historico:
    st.subheader("🗕️ Histórico de Atendimentos")
    with st.expander("Mostrar/ocultar histórico", expanded=False):
        st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True, height=420)

# ======= TAB EXPORTAR =======
with tab_exportar:
    st.subheader("📄 Exportar dados filtrados")
    buffer = BytesIO()
    df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
    st.download_button(
        "Baixar Excel com dados filtrados",
        data=buffer.getvalue(),
        file_name="dados_filtrados.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
