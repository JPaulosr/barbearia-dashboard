import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

# =============================
# Config
# =============================
st.set_page_config(page_title="Comparativo entre Funcionários", page_icon="🧑‍🤝‍🧑", layout="wide")
st.title("🧑‍🤝‍🧑 Comparativo entre Funcionários")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
MES_ORD = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
CUTOFF_COMBO = pd.Timestamp("2025-05-11")  # regra oficial
NOMES_IGNORAR = ["boliviano","brasileiro","menino","menino boliviano"]

def fmt_moeda(v: float) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    except Exception:
        return "R$ 0,00"

# =============================
# Conexão e carga
# =============================
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

    # Limpeza básica
    df.columns = [str(col).strip() for col in df.columns]
    # Data
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["Data"])
    # Valor
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    # Tipo/Funcionário/Cliente
    for c in ["Tipo","Funcionário","Cliente","Conta","StatusFiado","Combo","Serviço","Período","Fase"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).str.strip()

    # Derivadas
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.month.map({
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    })
    return df

df = carregar_dados()

# =============================
# Filtros (sidebar)
# =============================
st.sidebar.header("Filtros")

anos = sorted(df["Ano"].unique(), reverse=True)
ano_sel = st.sidebar.selectbox("📅 Ano", anos, index=0)

meses_disponiveis = [m for m in MES_ORD if m in df.loc[df["Ano"]==ano_sel, "Mês_Nome"].unique()]
meses_sel = st.sidebar.multiselect("🗓️ Meses", options=meses_disponiveis, default=meses_disponiveis)

funcs = sorted(df["Funcionário"].replace("", pd.NA).dropna().unique().tolist())
funcs_sel = st.sidebar.multiselect("👤 Funcionários", options=funcs, default=funcs or [])

tipos_disponiveis = sorted(df["Tipo"].replace("", pd.NA).dropna().unique().tolist()) or ["Serviço","Produto"]
tipos_sel = st.sidebar.multiselect("🧾 Tipo", options=tipos_disponiveis, default=tipos_disponiveis)

ignorar_fiado = st.sidebar.checkbox("Ignorar FIADO em aberto (conta='Fiado' com StatusFiado≠'Pago')", value=True)

# Aplica filtros
f = df[df["Ano"] == ano_sel].copy()
if meses_sel:
    f = f[f["Mês_Nome"].isin(meses_sel)]
if funcs_sel:
    f = f[f["Funcionário"].isin(funcs_sel)]
if tipos_sel:
    f = f[f["Tipo"].isin(tipos_sel)]
if ignorar_fiado:
    # Considera fiado pago; remove fiado em aberto
    mask_fiado_aberto = (f["Conta"].str.lower() == "fiado") & (~f["StatusFiado"].str.lower().eq("pago"))
    f = f[~mask_fiado_aberto]

# Guard rail
if f.empty:
    st.info("Sem dados para os filtros selecionados.")
    st.stop()

# =============================
# 📈 Receita Mensal por Funcionário
# =============================
st.subheader("📈 Receita Mensal por Funcionário")
receita_mensal = (
    f.groupby(["Funcionário","Mês","Mês_Nome"], as_index=False)["Valor"].sum()
    .sort_values("Mês")
)

# Média móvel de 3 meses (por funcionário) – ajuda a enxergar tendência
receita_mensal["MM3"] = (
    receita_mensal.sort_values(["Funcionário","Mês"])
    .groupby("Funcionário")["Valor"]
    .transform(lambda s: s.rolling(3, min_periods=1).mean())
)

fig = px.bar(
    receita_mensal,
    x="Mês_Nome", y="Valor", color="Funcionário",
    barmode="group", text_auto=True,
    category_orders={"Mês_Nome": MES_ORD}
)
st.plotly_chart(fig, use_container_width=True)

# Linha de tendência (média móvel) separada
fig_trend = px.line(
    receita_mensal.sort_values("Mês"),
    x="Mês_Nome", y="MM3", color="Funcionário",
    markers=True, category_orders={"Mês_Nome": MES_ORD},
    labels={"MM3": "Média móvel (3 meses)"}
)
st.plotly_chart(fig_trend, use_container_width=True)

# =============================
# 📋 Total de Atendimentos e Combos (regra 11/05/2025)
# =============================
st.subheader("📋 Total de Atendimentos por Funcionário (com lógica de 11/05/2025)")

# Pré-corte: cada linha = 1 atendimento
df_pre = f[f["Data"] < CUTOFF_COMBO].copy()
df_pre["Qtd_Serviços"] = 1

# Pós-corte: 1 atendimento/dia por Cliente+Data+Funcionário
df_pos = (
    f[f["Data"] >= CUTOFF_COMBO]
    .groupby(["Cliente","Data","Funcionário"], as_index=False)
    .agg(Qtd_Serviços=("Serviço","count"))
)

df_atends = pd.concat([
    df_pre[["Cliente","Data","Funcionário","Qtd_Serviços"]],
    df_pos[["Cliente","Data","Funcionário","Qtd_Serviços"]],
], ignore_index=True)

df_atends["Combo"] = (df_atends["Qtd_Serviços"] > 1).astype(int)
df_atends["Simples"] = (df_atends["Qtd_Serviços"] == 1).astype(int)

combo_simples = df_atends.groupby("Funcionário", as_index=False).agg(
    Total_Atendimentos=("Data","count"),
    Qtd_Combo=("Combo","sum"),
    Qtd_Simples=("Simples","sum")
)

c1, c2, c3 = st.columns(3)
st.dataframe(combo_simples, use_container_width=True, hide_index=True)
with c1:
    st.metric("Atendimentos (todos)", int(combo_simples["Total_Atendimentos"].sum()))
with c2:
    st.metric("Combos (soma)", int(combo_simples["Qtd_Combo"].sum()))
with c3:
    st.metric("Simples (soma)", int(combo_simples["Qtd_Simples"].sum()))

# =============================
# 💰 Receita Total no Ano
# =============================
st.subheader("💰 Receita Total no Ano por Funcionário")
receita_total = f.groupby("Funcionário", as_index=False)["Valor"].sum()
receita_total["Valor Formatado"] = receita_total["Valor"].map(fmt_moeda)
st.dataframe(receita_total[["Funcionário","Valor Formatado"]], use_container_width=True, hide_index=True)

# Diferença (se ambos presentes)
valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
if all(k in valores for k in ["JPaulo","Vinicius"]):
    dif = valores["JPaulo"] - valores["Vinicius"]
    st.metric(label=("JPaulo ganhou mais" if dif > 0 else "Vinicius ganhou mais"), value=fmt_moeda(abs(dif)))

# =============================
# 🏅 Top 10 Clientes por Receita (por Funcionário)
# =============================
st.subheader("🏅 Top 10 Clientes por Receita (por Funcionário)")
df_rank = f.copy()
df_rank = df_rank[~df_rank["Cliente"].str.lower().str.strip().isin(NOMES_IGNORAR)]

clientes_por_func = (
    df_rank.groupby(["Funcionário","Cliente"], as_index=False)["Valor"].sum()
    .sort_values(["Funcionário","Valor"], ascending=[True, False])
)

col1, col2 = st.columns(2)
for func, col in zip(funcs_sel or funcs, [col1, col2] if len(funcs_sel or funcs) > 1 else [st.container(), st.container()]):
    top = clientes_por_func[clientes_por_func["Funcionário"] == func].head(10).copy()
    if top.empty:
        continue
    top["Valor Formatado"] = top["Valor"].map(fmt_moeda)
    col.markdown(f"#### 👤 {func}")
    col.dataframe(top[["Cliente","Valor Formatado"]], use_container_width=True, hide_index=True)

# =============================
# 📆 Receita por Ano x Funcionário
# =============================
st.subheader("📆 Receita Total por Funcionário em Cada Ano")
receita_ano_func = (
    df.groupby(["Ano","Funcionário"], as_index=False)["Valor"].sum()
    .pivot(index="Ano", columns="Funcionário", values="Valor")
    .fillna(0)
    .sort_index(ascending=False)
)
tbl_fmt = receita_ano_func.applymap(fmt_moeda)
st.dataframe(tbl_fmt, use_container_width=True)

# =============================
# Export dos dados filtrados
# =============================
st.download_button(
    "⬇️ Baixar dados filtrados (CSV)",
    data=f.to_csv(index=False).encode("utf-8-sig"),
    file_name="comparativo_funcionarios_filtrado.csv",
    use_container_width=True
)

st.markdown("---")
st.caption("Dica: ative/desative o filtro de fiado em aberto para comparar competência vs. atendimento.")
