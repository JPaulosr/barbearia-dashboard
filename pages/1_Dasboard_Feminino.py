# 6F_Dashboard_Feminino.py
# Dashboard Feminino — lê a aba "Base de Dados Feminino" da mesma planilha do salão

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

# =========================
# CONFIGURAÇÃO GERAL
# =========================
st.set_page_config(
    page_title="Dashboard Feminino",
    page_icon="💅",
    layout="wide"
)
st.title("💅 Dashboard Feminino")

PLOTLY_TEMPLATE = "plotly_dark"  # visual escuro

# ID da planilha principal (CORRETO)
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_NOME = "Base de Dados Feminino"
GID_FEMININO = "400923272"

# =========================
# CARREGAMENTO DE DADOS
# =========================
@st.cache_data(ttl=300)
def carregar_dados():
    """
    Tenta carregar com Service Account via gspread (se existir em st.secrets).
    Caso não tenha, faz fallback para CSV público do Google Sheets.
    """
    df = None
    usou_gspread = False

    # 1) Tentativa com Service Account
    try:
        from google.oauth2.service_account import Credentials
        import gspread
        from gspread_dataframe import get_as_dataframe

        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"],
                scopes=[
                    "https://www.googleapis.com/auth/spreadsheets.readonly",
                    "https://www.googleapis.com/auth/drive.readonly",
                ],
            )
            gc = gspread.authorize(creds)
            ws = gc.open_by_key(SHEET_ID).worksheet(ABA_NOME)
            df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str)
            usou_gspread = True
    except Exception as e:
        # Mostra aviso mas segue para fallback
        st.warning("Não foi possível usar a Service Account nesta página. Tentando via CSV público…")

    # 2) Fallback CSV (exige compartilhamento público de leitura)
    if df is None or df.empty:
        url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID_FEMININO}"
        try:
            df = pd.read_csv(url_csv, dtype=str)
        except Exception as e:
            raise RuntimeError(
                "Falha ao carregar a aba via CSV. "
                "Verifique se o ID da planilha está correto e se a aba está compartilhada para leitura por link."
            ) from e

    # ---------- Padronizações ----------
    # Data
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)

    # Valor numérico (aceita R$, espaços, NBSP etc.)
    if "Valor" in df.columns:
        v = df["Valor"].astype(str)
        v = v.str.replace(r"[^\d,.\-]", "", regex=True)  # remove símbolos
        v = v.str.replace(".", "", regex=False)          # milhar
        v = v.str.replace(",", ".", regex=False)         # vírgula -> ponto
        df["Valor"] = pd.to_numeric(v, errors="coerce")

    # Limpa espaços
    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str).str.strip()

    # Remove linhas totalmente vazias
    df = df.dropna(how="all")

    # Informação útil no topo
    origem = "Service Account" if usou_gspread else "CSV público"
    st.caption(f"Fonte de dados: **{origem}** · Linhas lidas: **{len(df)}**")
    return df


df_raw = carregar_dados()

if df_raw.empty or ("Data" not in df_raw.columns) or df_raw["Data"].isna().all():
    st.info("A aba **Base de Dados Feminino** está vazia (ou sem datas válidas). Adicione registros para ver o dashboard.")
    st.stop()

# =========================
# FILTROS (sidebar)
# =========================
with st.sidebar:
    st.header("Filtros")

    min_data = pd.to_datetime(df_raw["Data"]).min()
    max_data = pd.to_datetime(df_raw["Data"]).max()

    periodo = st.date_input(
        "Período",
        value=(min_data.date() if pd.notna(min_data) else date.today(),
               max_data.date() if pd.notna(max_data) else date.today())
    )

    def unique_sorted(col):
        if col not in df_raw.columns:
            return []
        vals = [x for x in df_raw[col].dropna().unique() if str(x).strip() != ""]
        return sorted(vals, key=lambda s: str(s).lower())

    servicos_sel = st.multiselect("Serviço", unique_sorted("Serviço"))
    clientes_sel = st.multiselect("Cliente", unique_sorted("Cliente"))
    funcionarios_sel = st.multiselect("Funcionário", unique_sorted("Funcionário"))
    contas_sel = st.multiselect("Forma de pagamento (Conta)", unique_sorted("Conta"))
    tipos_sel = st.multiselect("Tipo (Produto/Serviço)", unique_sorted("Tipo"))

    # Remover nomes genéricos apenas para rankings
    NOMES_GENERICOS = {"boliviano", "brasileiro", "menino", "menina", "cliente", "clientes"}

# Aplica filtros
mask = (
    (df_raw["Data"] >= pd.to_datetime(periodo[0])) &
    (df_raw["Data"] <= pd.to_datetime(periodo[1]))
)

def aplica_multiselect(df, coluna, selecionados):
    if coluna not in df.columns:
        return pd.Series(True, index=df.index)
    if selecionados:
        return df[coluna].isin(selecionados)
    return pd.Series(True, index=df.index)

mask &= aplica_multiselect(df_raw, "Serviço", servicos_sel)
mask &= aplica_multiselect(df_raw, "Cliente", clientes_sel)
mask &= aplica_multiselect(df_raw, "Funcionário", funcionarios_sel)
mask &= aplica_multiselect(df_raw, "Conta", contas_sel)
mask &= aplica_multiselect(df_raw, "Tipo", tipos_sel)

df = df_raw[mask].copy()

# Helper: atendimentos únicos por cliente+data (uma visita/dia)
def contar_atendimentos(df_in):
    if ("Cliente" not in df_in.columns) or ("Data" not in df_in.columns):
        return 0
    aux = df_in.dropna(subset=["Cliente", "Data"]).copy()
    aux["DataDia"] = aux["Data"].dt.date
    return aux.groupby(["Cliente", "DataDia"]).ngroup().nunique()

# =========================
# MÉTRICAS (top KPIs)
# =========================
receita = float(np.nansum(df["Valor"])) if "Valor" in df.columns else 0.0
atendimentos = contar_atendimentos(df)
ticket_medio = (receita / atendimentos) if atendimentos > 0 else 0.0

c1, c2, c3, c4 = st.columns(4)
c1.metric("Receita no período", f"R$ {receita:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
c2.metric("Atendimentos (únicos)", f"{atendimentos}")
c3.metric("Ticket médio", f"R$ {ticket_medio:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
c4.metric("Registros (linhas)", f"{len(df):,}".replace(",", "."))

# =========================
# GRÁFICOS PRINCIPAIS
# =========================
fig_mes = fig_serv = fig_func = fig_conta = fig_dia = None

if ("Data" in df.columns) and ("Valor" in df.columns):
    base_mes = df.copy()
    base_mes["Ano-Mês"] = base_mes["Data"].dt.to_period("M").astype(str)
    gm = base_mes.groupby("Ano-Mês", as_index=False)["Valor"].sum()
    fig_mes = px.bar(gm, x="Ano-Mês", y="Valor", title="Receita por mês", template=PLOTLY_TEMPLATE)
    fig_mes.update_layout(xaxis_title="", yaxis_title="R$")

if ("Serviço" in df.columns) and ("Valor" in df.columns):
    gs = df.groupby("Serviço", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False).head(15)
    fig_serv = px.bar(gs, x="Serviço", y="Valor", title="Receita por serviço (Top 15)", template=PLOTLY_TEMPLATE)
    fig_serv.update_layout(xaxis_title="", yaxis_title="R$")

if ("Funcionário" in df.columns) and ("Valor" in df.columns):
    gf = df.groupby("Funcionário", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    fig_func = px.bar(gf, x="Funcionário", y="Valor", title="Receita por funcionário", template=PLOTLY_TEMPLATE)
    fig_func.update_layout(xaxis_title="", yaxis_title="R$")

if ("Conta" in df.columns) and ("Valor" in df.columns) and not df["Conta"].isna().all():
    gc = df.groupby("Conta", as_index=False)["Valor"].sum()
    if not gc.empty:
        fig_conta = px.pie(gc, names="Conta", values="Valor", title="Receita por forma de pagamento", template=PLOTLY_TEMPLATE, hole=0.3)

if ("Data" in df.columns) and ("Valor" in df.columns):
    gd = df.groupby(df["Data"].dt.date, as_index=False)["Valor"].sum()
    if not gd.empty:
        fig_dia = px.line(gd, x="Data", y="Valor", markers=True, title="Evolução diária de receita", template=PLOTLY_TEMPLATE)
        fig_dia.update_layout(xaxis_title="", yaxis_title="R$")

g1, g2 = st.columns([1, 1])
with g1:
    if fig_mes: st.plotly_chart(fig_mes, use_container_width=True)
    if fig_serv: st.plotly_chart(fig_serv, use_container_width=True)
with g2:
    if fig_func: st.plotly_chart(fig_func, use_container_width=True)
    if fig_conta: st.plotly_chart(fig_conta, use_container_width=True)
    if fig_dia: st.plotly_chart(fig_dia, use_container_width=True)

# =========================
# RANKING DE CLIENTES
# =========================
st.subheader("🏆 Top clientes (por receita)")
df_rank = df.copy()

if "Cliente" in df_rank.columns:
    df_rank["Cliente_limpo"] = df_rank["Cliente"].str.strip().str.lower()
    df_rank = df_rank[~df_rank["Cliente_limpo"].isin({"boliviano","brasileiro","menino","menina","cliente","clientes"})]
    df_rank = df_rank.drop(columns=["Cliente_limpo"], errors="ignore")

if ("Cliente" in df_rank.columns) and ("Valor" in df_rank.columns):
    top_clientes = (
        df_rank.groupby("Cliente", as_index=False)
        .agg(Receita=("Valor", "sum"))
        .sort_values("Receita", ascending=False)
        .head(20)
    )
    if "Data" in df_rank.columns:
        aux = df_rank.dropna(subset=["Cliente", "Data"]).copy()
        aux["DataDia"] = aux["Data"].dt.date
        atend_por_cli = aux.groupby("Cliente")["DataDia"].nunique().reset_index().rename(columns={"DataDia": "Atendimentos"})
        top_clientes = top_clientes.merge(atend_por_cli, on="Cliente", how="left")
        top_clientes["Ticket médio"] = top_clientes["Receita"] / top_clientes["Atendimentos"].replace(0, np.nan)

    def moeda(x):
        if pd.isna(x): return "-"
        return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    top_clientes_fmt = top_clientes.copy()
    if "Receita" in top_clientes_fmt.columns:
        top_clientes_fmt["Receita"] = top_clientes_fmt["Receita"].apply(moeda)
    if "Ticket médio" in top_clientes_fmt.columns:
        top_clientes_fmt["Ticket médio"] = top_clientes_fmt["Ticket médio"].apply(moeda)

    st.dataframe(top_clientes_fmt, use_container_width=True, hide_index=True)

    cA, cB = st.columns(2)
    with cA:
        st.download_button(
            "⬇️ Baixar ranking (CSV)",
            data=top_clientes.to_csv(index=False).encode("utf-8"),
            file_name="top_clientes_feminino.csv",
            mime="text/csv",
            use_container_width=True
        )
    with cB:
        st.download_button(
            "⬇️ Baixar base filtrada (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="base_feminino_filtrada.csv",
            mime="text/csv",
            use_container_width=True
        )
else:
    st.info("Ainda não há dados suficientes para montar o ranking de clientes.")

# =========================
# INSIGHTS RÁPIDOS
# =========================
st.subheader("✨ Insights rápidos")
insights = []

if ("Tipo" in df.columns) and ("Valor" in df.columns):
    mix = df.groupby("Tipo", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    if not mix.empty:
        maior = mix.iloc[0]
        insights.append(
            f"Maior receita no período veio de **{maior['Tipo']}** (R$ {maior['Valor']:,.2f})."
            .replace(",", "X").replace(".", ",").replace("X", ".")
        )

if ("Serviço" in df.columns) and ("Valor" in df.columns) and not df["Serviço"].isna().all():
    s = df.groupby("Serviço", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    if not s.empty:
        insights.append(f"Serviço campeão: **{s.iloc[0]['Serviço']}**.")

if ("Funcionário" in df.columns) and ("Valor" in df.columns) and not df["Funcionário"].isna().all():
    f = df.groupby("Funcionário", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    if not f.empty:
        insights.append(f"Maior faturamento por: **{f.iloc[0]['Funcionário']}**.")

if ("Data" in df.columns) and ("Valor" in df.columns):
    m = df.copy()
    m["Ano-Mês"] = m["Data"].dt.to_period("M").astype(str)
    mm = m.groupby("Ano-Mês", as_index=False)["Valor"].sum().sort_values("Valor", ascending=False)
    if not mm.empty:
        insights.append(f"Melhor mês do filtro: **{mm.iloc[0]['Ano-Mês']}**.")

if insights:
    for i in insights:
        st.markdown(f"- {i}")
else:
    st.write("Sem insights ainda — adicione registros 😉")
