# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO
from babel.dates import format_date  # meses pt-BR
import re

st.set_page_config(layout="wide", page_title="Detalhamento do Cliente", page_icon="🧾")
st.title("📌 Detalhamento do Cliente")

# =========================
# Constantes
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"

# =========================
# Funções auxiliares
# =========================
def parse_valor_col(series: pd.Series) -> pd.Series:
    """Converte valores pt-BR ('1.234,56', 'R$ 25,00') em float."""
    def parse_cell(x):
        if pd.isna(x): return 0.0
        if isinstance(x, (int, float)): return float(x)
        s = str(x).strip()
        if not s: return 0.0
        s = s.replace("R$", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1:
            left, last = s.rsplit(".", 1)
            left = left.replace(".", "")
            s = f"{left}.{last}"
        else:
            s = s.replace(",", ".")
        return pd.to_numeric(s, errors="coerce")
    return series.map(parse_cell).fillna(0.0)

def brl(x: float) -> str:
    return f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def _norm_name(s: str) -> str:
    return re.sub(r"[\W_]+", "", str(s).strip().lower())

# =========================
# GOOGLE SHEETS
# =========================
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

    # Datas
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    # Valor numérico (serviços/produtos)
    df["ValorNumBruto"] = parse_valor_col(df["Valor"]) if "Valor" in df.columns else 0.0

    # Caixinha (colunas robustas)
    cand_cx = ["CaixinhaDia", "Caixinha_Fundo", "CaixinhaFundo", "Caixinha", "Gorjeta"]
    presentes = [c for c in cand_cx if c in df.columns]
    for c in presentes:
        df[c] = parse_valor_col(df[c])
    df["CaixinhaDiaTotal"] = df[presentes].sum(axis=1) if presentes else 0.0
    df.attrs["__cx_cols__"] = presentes

    # Normaliza campos chave
    for col in ["Cliente", "Funcionário", "Tipo", "Serviço", "Período"]:
        if col in df.columns:
            df[col] = df[col].astype(str).fillna("").str.strip()

    return df

df = carregar_dados()

# =========================
# Filtro de pagamento (Pagos / Fiado / Tudo)
# =========================
def norm_pair(df, name):
    if name not in df.columns:
        return pd.Series("", index=df.index), pd.Series("", index=df.index)
    s = df[name].astype(str).str.strip().fillna("")
    s_low = (s.str.lower()
               .str.replace("ã", "a")
               .str.replace("á", "a")
               .str.replace("â", "a")
               .str.replace("ç", "c"))
    return s, s_low

col_conta = "Conta"
col_status_fiado = "StatusFiado"
col_data_pag = "DataPagamento"

serie_conta_raw, serie_conta = norm_pair(df, col_conta)
serie_status_raw, serie_status = norm_pair(df, col_status_fiado)

# DataPagamento preenchida?
if col_data_pag in df.columns:
    s_pag = df[col_data_pag]
    if pd.api.types.is_datetime64_any_dtype(s_pag):
        mask_datapag = s_pag.notna()
    else:
        mask_datapag = s_pag.astype(str).str.strip().ne("") & s_pag.notna()
else:
    mask_datapag = pd.Series(False, index=df.index)

# Regras
mask_conta_fiado = serie_conta.eq("fiado")  # exatamente como na planilha
mask_status_pago = serie_status.str.contains("pag", na=False)  # "pago", "pagamento", etc.

mask_fiado_quitado = mask_conta_fiado & (mask_status_pago | mask_datapag)
mask_fiado_em_aberto = mask_conta_fiado & ~mask_fiado_quitado
mask_nao_fiado = ~mask_conta_fiado

st.sidebar.subheader("Filtro de pagamento")
opcao_pagto = st.sidebar.radio(
    label="",
    options=["Apenas pagos", "Apenas fiado", "Incluir tudo"],
    index=0,
    help="Controla o que entra nos gráficos e somas."
)

# Base para valores/gráficos
if opcao_pagto == "Apenas pagos":
    base_val = df[mask_nao_fiado | mask_fiado_quitado].copy()
elif opcao_pagto == "Apenas fiado":
    base_val = df[mask_fiado_em_aberto].copy()
else:
    base_val = df.copy()

aplicar_no_historico = st.sidebar.checkbox("Aplicar no histórico (tabela)", value=False)

with st.sidebar.expander("Ver contagem (conferência)"):
    st.write(f"Total linhas: **{len(df)}**")
    st.write(f"Fiado em aberto: **{int(mask_fiado_em_aberto.sum())}**")
    st.write(f"Fiado quitado: **{int(mask_fiado_quitado.sum())}**")
    st.write(f"Não fiado: **{int(mask_nao_fiado.sum())}**")
    st.caption("Colunas de Caixinha: " + ", ".join(df.attrs.get("__cx_cols__", [])))

base_val["ValorNum"] = base_val["ValorNumBruto"].astype(float)

# =========================
# Seleção do Cliente
# =========================
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
if not clientes_disponiveis:
    st.warning("Não há clientes na base.")
    st.stop()

cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox(
    "👤 Selecione o cliente",
    clientes_disponiveis,
    index=clientes_disponiveis.index(cliente_default)
)

# =========================
# Imagem do cliente
# =========================
def buscar_link_foto(nome):
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet("clientes_status")
        df_status = get_as_dataframe(aba_status).dropna(how="all")
        df_status.columns = [str(col).strip() for col in df_status.columns]
        foto = df_status[df_status["Cliente"] == nome]["Foto"].dropna().values
        return foto[0] if len(foto) > 0 else None
    except Exception:
        return None

link_foto = buscar_link_foto(cliente)
if link_foto:
    try:
        response = requests.get(link_foto, timeout=8)
        img = Image.open(BytesIO(response.content))
        st.image(img, caption=cliente, width=200)
    except Exception:
        st.warning("Erro ao carregar imagem.")
else:
    st.info("Cliente sem imagem cadastrada.")

# =========================
# Dados do cliente (tabela e bases)
# =========================
if aplicar_no_historico:
    df_cliente = base_val[base_val["Cliente"] == cliente].copy()
else:
    df_cliente = df[df["Cliente"] == cliente].copy()

df_cliente_val = base_val[base_val["Cliente"] == cliente].copy()  # gráficos/somas

st.subheader(f"📅 Histórico de atendimentos — {cliente}")
colunas_exibir = ["Data_str", "Serviço", "Tipo", "Valor", "Funcionário", "Período"]
colunas_exibir = [c for c in colunas_exibir if c in df_cliente.columns]
st.dataframe(
    df_cliente.sort_values("Data", ascending=False)[colunas_exibir].rename(columns={"Data_str": "Data"}),
    use_container_width=True
)

# =========================
# ⏰ Atendimentos por Período (Manhã/Tarde/Noite) – sem "Outro"
# =========================
def _normalize_period_value(x: str) -> str | None:
    s = str(x).strip().lower()
    s = (s.replace("ã", "a").replace("á", "a").replace("â", "a").replace("é", "e"))
    if s.startswith("man"):   # manha, manhã
        return "Manhã"
    if s.startswith("tar"):   # tarde
        return "Tarde"
    if s.startswith("noi"):   # noite
        return "Noite"
    return None  # <<-- em vez de "Outro", ignora

# detecta a coluna de período
periodo_col = None
for c in df_cliente_val.columns:
    if re.sub(r"[\W_]+", "", str(c).strip().lower()) in {
        "periodo","período","periodododia","periodo_dia","periodoatendimento","turno","faixahoraria"
    }:
        periodo_col = c
        break

if periodo_col:
    st.subheader("⏰ Atendimentos por Período")
    df_per = df_cliente_val[[periodo_col]].copy()
    df_per["__periodo__"] = df_per[periodo_col].map(_normalize_period_value)

    # mantém só Manhã/Tarde/Noite
    validos = {"Manhã", "Tarde", "Noite"}
    df_per = df_per[df_per["__periodo__"].isin(validos)]

    ordem = ["Manhã", "Tarde", "Noite"]
    counts = df_per["__periodo__"].value_counts()
    dist_periodo = pd.DataFrame({
        "Período": ordem,
        "Qtd": [int(counts.get(p, 0)) for p in ordem]
    })

    if dist_periodo["Qtd"].sum() == 0:
        st.info("Sem informação de período (Manhã/Tarde/Noite) para este cliente nos filtros atuais.")
        periodo_preferido = "Sem registro"
    else:
        fig_per = px.bar(dist_periodo, x="Período", y="Qtd", text="Qtd")
        fig_per.update_layout(height=320, yaxis_title="Qtde", xaxis_title=None,
                              margin=dict(l=10, r=10, t=30, b=10), showlegend=False)
        st.plotly_chart(fig_per, use_container_width=True)
        periodo_preferido = dist_periodo.sort_values("Qtd", ascending=False).iloc[0]["Período"]
else:
    st.info("Coluna de Período (Manhã/Tarde/Noite) não encontrada.")
    periodo_preferido = "Sem registro"
    
# =========================
# 🎁 Caixinha do Cliente
# =========================
st.subheader("🎁 Caixinha do Cliente")
if "CaixinhaDiaTotal" not in df_cliente_val.columns:
    st.info("Não foram encontradas colunas de caixinha para este cliente.")
else:
    base_cx = df_cliente_val.copy()
    cx_total = float(base_cx["CaixinhaDiaTotal"].sum())
    cx_jp = float(base_cx.loc[base_cx["Funcionário"].str.casefold() == FUNC_JPAULO.casefold(), "CaixinhaDiaTotal"].sum())
    cx_vini = float(base_cx.loc[base_cx["Funcionário"].str.casefold() == FUNC_VINICIUS.casefold(), "CaixinhaDiaTotal"].sum())

    cc1, cc2, cc3 = st.columns(3)
    cc1.metric("Total de Caixinha (cliente)", brl(cx_total))
    cc2.metric("Caixinha • JPaulo", brl(cx_jp))
    cc3.metric("Caixinha • Vinicius", brl(cx_vini))

    # Gráfico por funcionário
    df_cx_func = (
        base_cx.groupby("Funcionário", dropna=False)["CaixinhaDiaTotal"]
        .sum().reset_index().rename(columns={"CaixinhaDiaTotal": "Caixinha"})
        .sort_values("Caixinha", ascending=False)
    )
    if not df_cx_func.empty and df_cx_func["Caixinha"].sum() > 0:
        fig_cx = px.bar(df_cx_func, x="Funcionário", y="Caixinha", text="Caixinha", labels={"Caixinha": "R$"})
        fig_cx.update_layout(height=340, yaxis_title="Caixinha (R$)", showlegend=False, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_cx, use_container_width=True)

    # Tabela detalhada
    cols_exist = [c for c in ["CaixinhaDia", "Caixinha_Fundo", "CaixinhaFundo"] if c in base_cx.columns]
    mostrar_cols = ["Data_str", "Funcionário"] + cols_exist + ["CaixinhaDiaTotal"]
    df_cx_rows = base_cx[base_cx["CaixinhaDiaTotal"] > 0][mostrar_cols].copy()
    if not df_cx_rows.empty:
        df_cx_rows = df_cx_rows.rename(columns={"Data_str": "Data", "CaixinhaDiaTotal": "Total Caixinha"})
        for c in cols_exist + ["Total Caixinha"]:
            df_cx_rows[c] = df_cx_rows[c].astype(float).map(brl)
        st.dataframe(df_cx_rows.sort_values("Data", ascending=False), use_container_width=True, hide_index=True)

# =========================
# 📊 Receita mensal (com opção de somar caixinha)
# =========================
st.subheader("📊 Receita mensal")
somar_cx_mensal = st.checkbox(
    "Somar caixinha na receita mensal do cliente",
    value=True,
    help="Quando ligado, a receita mensal considera Valor + Caixinha do cliente."
)

if df_cliente_val.empty:
    st.info("Sem valores recebidos para exibir.")
else:
    df_cliente_val["ValorNum"] = df_cliente_val["ValorNum"].astype(float)
    if "CaixinhaDiaTotal" not in df_cliente_val.columns:
        df_cliente_val["CaixinhaDiaTotal"] = 0.0
    df_cliente_val["CaixinhaDiaTotal"] = df_cliente_val["CaixinhaDiaTotal"].astype(float).fillna(0.0)

    base_col = "ValorNum"
    if somar_cx_mensal:
        df_cliente_val["ValorComCx"] = df_cliente_val["ValorNum"] + df_cliente_val["CaixinhaDiaTotal"]
        base_col = "ValorComCx"

    df_cliente_val["Data_Ref_Mensal"] = df_cliente_val["Data"].dt.to_period("M").dt.to_timestamp()
    receita_mensal = (
        df_cliente_val.groupby("Data_Ref_Mensal")[base_col]
        .sum()
        .reset_index()
        .rename(columns={base_col: "ValorGrafico"})
    )
    receita_mensal["Mês_Ano"] = receita_mensal["Data_Ref_Mensal"].apply(
        lambda d: format_date(d, format="MMMM 'de' y", locale="pt_BR").capitalize()
    )
    receita_mensal["Valor_str"] = receita_mensal["ValorGrafico"].apply(brl)
    subt = " (inclui caixinha)" if somar_cx_mensal else ""
    fig_receita = px.bar(
        receita_mensal,
        x="Mês_Ano",
        y="ValorGrafico",
        text="Valor_str",
        labels={"ValorGrafico": f"Receita{subt} (R$)", "Mês_Ano": "Mês"},
    )
    fig_receita.update_traces(textposition="inside")
    fig_receita.update_layout(height=400)
    st.plotly_chart(fig_receita, use_container_width=True)

# =========================
# Receita por Serviço e Produto
# =========================
st.subheader("📊 Receita por Serviço e Produto")
if df_cliente_val.empty:
    st.info("Sem valores recebidos para exibir.")
else:
    df_tipos = df_cliente_val[["Serviço", "Tipo", "ValorNum"]].copy()
    receita_geral = (
        df_tipos.groupby(["Serviço", "Tipo"])["ValorNum"]
        .sum()
        .reset_index()
        .sort_values("ValorNum", ascending=False)
    )
    fig_receita_tipos = px.bar(
        receita_geral,
        x="Serviço",
        y="ValorNum",
        color="Tipo",
        text=receita_geral["ValorNum"].apply(brl),
        labels={"ValorNum": "Receita (R$)", "Serviço": "Item"},
        barmode="group"
    )
    fig_receita_tipos.update_traces(textposition="outside")
    st.plotly_chart(fig_receita_tipos, use_container_width=True)

# =========================
# Atendimentos por Funcionário (contagem)
# =========================
st.subheader("📊 Atendimentos por Funcionário")
atendimentos_unicos = df_cliente.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
atendimentos_por_funcionario = atendimentos_unicos["Funcionário"].value_counts().reset_index()
atendimentos_por_funcionario.columns = ["Funcionário", "Qtd Atendimentos"]
st.dataframe(atendimentos_por_funcionario, use_container_width=True)

# =========================
# Resumo de Atendimentos (combos/simples)
# =========================
st.subheader("📋 Resumo de Atendimentos")
df_cliente_dt = df[df["Cliente"] == cliente].copy()
resumo = df_cliente_dt.groupby("Data").agg(
    Qtd_Serviços=("Serviço", "count"),
    Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum())
).reset_index()
resumo["Qtd_Combo"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
resumo["Qtd_Simples"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)
resumo_final = pd.DataFrame({
    "Total Atendimentos": [resumo.shape[0]],
    "Qtd Combos": [resumo["Qtd_Combo"].sum()],
    "Qtd Simples": [resumo["Qtd_Simples"].sum()]
})
st.dataframe(resumo_final, use_container_width=True)

# =========================
# Frequência de atendimento (sem duplicar nos Insights)
# =========================
st.subheader("📈 Frequência de Atendimento")
data_corte = pd.to_datetime("2025-05-11")
df_antes = df_cliente_dt[df_cliente_dt["Data"] < data_corte].copy()
df_depois = df_cliente_dt[df_cliente_dt["Data"] >= data_corte].drop_duplicates(subset=["Data"]).copy()
df_freq = pd.concat([df_antes, df_depois]).sort_values("Data")

datas = df_freq["Data"].tolist()
if len(datas) >= 2:
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (pd.Timestamp.today().normalize() - ultimo_atendimento).days
    status = (
        "🟢 Em dia" if dias_desde_ultimo <= media_freq
        else ("🟠 Pouco atrasado" if dias_desde_ultimo <= media_freq * 1.5 else "🔴 Muito atrasado")
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Último Atendimento", ultimo_atendimento.strftime("%d/%m/%Y"))
    col2.metric("📊 Frequência Média", f"{media_freq:.1f} dias")
    col3.metric("⏱️ Desde Último", dias_desde_ultimo)
    col4.metric("📌 Status", status)
else:
    st.info("Cliente possui apenas um atendimento.")

# =========================
# 💡 Insights Adicionais (sem duplicar frequência)
# =========================
st.subheader("💡 Insights Adicionais")
meses_ativos = df_cliente["Mês_Ano"].nunique()
gasto_mensal_medio = (df_cliente_val["ValorNum"].sum() / meses_ativos) if meses_ativos > 0 else 0
status_vip = "Sim ⭐" if gasto_mensal_medio >= 70 else "Não"
mais_frequente = df_cliente["Funcionário"].mode()[0] if not df_cliente["Funcionário"].isna().all() else "Indefinido"
ticket_medio = df_cliente_val["ValorNum"].mean() if not df_cliente_val.empty else 0
visitas_periodo = df_cliente_val["Data"].dt.normalize().nunique()

col5, col6, col7 = st.columns(3)
col5.metric("🏅 Cliente VIP", status_vip)
col6.metric("💇 Mais atendido por", mais_frequente)
col7.metric("⏰ Período mais frequente", periodo_preferido)

col8, col9, col10 = st.columns(3)
col8.metric("💸 Ticket Médio", brl(ticket_medio))
col9.metric("📆 Visitas no Período", visitas_periodo)
if "CaixinhaDiaTotal" in df_cliente_val.columns:
    col10.metric("🎁 Caixinha (Cliente)", brl(float(df_cliente_val["CaixinhaDiaTotal"].astype(float).sum())))
else:
    col10.metric("🎁 Caixinha (Cliente)", brl(0.0))
