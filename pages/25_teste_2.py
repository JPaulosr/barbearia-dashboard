import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🧑‍🤝‍🧑 Comparativo entre Funcionários")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
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

    # padroniza colunas
    df.columns = [str(col).strip() for col in df.columns]

    # datas
    df["Data"] = pd.to_datetime(df.get("Data"), errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.month.map({
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    })

    # valor numérico
    if "Valor" in df.columns:
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    else:
        df["Valor"] = 0.0

    # normaliza coluna de forma de pagamento/conta
    # tenta "Conta" primeiro; se não houver, tenta "Forma de Pagamento"
    conta_col = "Conta" if "Conta" in df.columns else ("Forma de Pagamento" if "Forma de Pagamento" in df.columns else None)
    if conta_col:
        df["Conta_norm"] = (
            df[conta_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .replace({"nan": ""})
        )
    else:
        df["Conta_norm"] = ""

    # normaliza funcionário/cliente/serviço
    for c in ["Funcionário", "Cliente", "Serviço"]:
        if c not in df.columns:
            df[c] = ""

    return df

df = carregar_dados()

# =============================
# 🔎 Filtro por ano e FIADO
# =============================
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)

col_f1, col_f2 = st.columns([1, 3])
modo_pag = col_f1.radio(
    "Filtro de pagamento",
    ["Apenas pagos", "Apenas fiado", "Incluir tudo"],
    index=0,
    help="Aplica o filtro a todos os gráficos e tabelas desta página."
)

df_filtrado = df[df["Ano"] == ano].copy()

# aplica FIADO
# considera fiado quando Conta_norm == 'fiado'
if modo_pag == "Apenas pagos":
    df_filtrado = df_filtrado[df_filtrado["Conta_norm"] != "fiado"]
elif modo_pag == "Apenas fiado":
    df_filtrado = df_filtrado[df_filtrado["Conta_norm"] == "fiado"]
# "Incluir tudo" não filtra

# =============================
# 📈 Receita Mensal por Funcionário
# =============================
st.subheader("📈 Receita Mensal por Funcionário")
if not df_filtrado.empty:
    receita_mensal = (
        df_filtrado.groupby(["Funcionário", "Mês", "Mês_Nome"], as_index=False)["Valor"].sum()
        .sort_values("Mês")
    )
    fig = px.bar(
        receita_mensal,
        x="Mês_Nome",
        y="Valor",
        color="Funcionário",
        barmode="group",
        text_auto=True,
        category_orders={"Mês_Nome": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]}
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados para os filtros selecionados.")

# =============================
# 📋 Total de Atendimentos e Combos com lógica de 11/05
# =============================
st.subheader("📋 Total de Atendimentos por Funcionário")

df_pre = df_filtrado[df_filtrado["Data"] < pd.Timestamp("2025-05-11")].copy()
df_pre["Qtd_Serviços"] = 1

df_pos = df_filtrado[df_filtrado["Data"] >= pd.Timestamp("2025-05-11")].copy()
df_pos = df_pos.groupby(["Cliente", "Data", "Funcionário"]).agg(Qtd_Serviços=("Serviço", "count")).reset_index()

df_atendimentos = pd.concat([
    df_pre[["Cliente", "Data", "Funcionário", "Qtd_Serviços"]],
    df_pos[["Cliente", "Data", "Funcionário", "Qtd_Serviços"]]
], ignore_index=True)

df_atendimentos["Combo"] = (df_atendimentos["Qtd_Serviços"] > 1).astype(int)
df_atendimentos["Simples"] = (df_atendimentos["Qtd_Serviços"] == 1).astype(int)

combo_simples = df_atendimentos.groupby("Funcionário", as_index=False).agg(
    Total_Atendimentos=("Data", "count"),
    Qtd_Combo=("Combo", "sum"),
    Qtd_Simples=("Simples", "sum")
)

col1, col2 = st.columns(2)
for _, row in combo_simples.iterrows():
    if row["Funcionário"] == "JPaulo":
        col1.metric("Atendimentos - JPaulo", int(row["Total_Atendimentos"]))
        col1.metric("Combos - JPaulo", int(row["Qtd_Combo"]))
        col1.metric("Simples - JPaulo", int(row["Qtd_Simples"]))
    elif row["Funcionário"] == "Vinicius":
        col2.metric("Atendimentos - Vinicius", int(row["Total_Atendimentos"]))
        col2.metric("Combos - Vinicius", int(row["Qtd_Combo"]))
        col2.metric("Simples - Vinicius", int(row["Qtd_Simples"]))

st.dataframe(combo_simples, use_container_width=True)

# =============================
# 💰 Receita Total no Ano
# =============================
st.subheader("💰 Receita Total no Ano por Funcionário")
receita_total = df_filtrado.groupby("Funcionário", as_index=False)["Valor"].sum()
receita_total["Valor Formatado"] = receita_total["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)
st.dataframe(receita_total[["Funcionário", "Valor Formatado"]], use_container_width=True)

# =============================
# 📊 Diferença de Receita
# =============================
st.subheader("📊 Diferença de Receita (R$)")
valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
if "JPaulo" in valores and "Vinicius" in valores:
    dif = valores["JPaulo"] - valores["Vinicius"]
    label = "JPaulo ganhou mais" if dif > 0 else ("Vinicius ganhou mais" if dif < 0 else "Empate")
    st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# =============================
# 🏅 Top 10 Clientes por Receita
# =============================
st.subheader("🏅 Top 10 Clientes por Receita (por Funcionário)")
nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
df_rank = df_filtrado[~df_filtrado["Cliente"].astype(str).str.lower().str.strip().isin(nomes_ignorar)]

clientes_por_func = (
    df_rank.groupby(["Funcionário", "Cliente"], as_index=False)["Valor"].sum()
    .sort_values(["Funcionário", "Valor"], ascending=[True, False])
)

col1, col2 = st.columns(2)
for func, col in zip(["JPaulo", "Vinicius"], [col1, col2]):
    top_clientes = clientes_por_func[clientes_por_func["Funcionário"] == func].head(10).copy()
    top_clientes["Valor Formatado"] = top_clientes["Valor"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
    col.markdown(f"#### 👤 {func}")
    col.dataframe(top_clientes[["Cliente", "Valor Formatado"]], use_container_width=True)

# =============================
# 📆 Receita Total por Funcionário em Cada Ano
# =============================
st.subheader("📆 Receita Total por Funcionário em Cada Ano")
receita_ano_func = (
    df.groupby(["Ano", "Funcionário"])["Valor"]
    .sum()
    .reset_index()
    .pivot(index="Ano", columns="Funcionário", values="Valor")
    .fillna(0)
    .sort_index(ascending=False)
)

receita_formatada = receita_ano_func.copy()
for col in receita_formatada.columns:
    receita_formatada[col] = receita_formatada[col].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
st.dataframe(receita_formatada, use_container_width=True)

# =============================
# Rodapé
# =============================
st.markdown("""
---
⬅️ Use o menu lateral para acessar outras páginas ou detalhes por cliente.
""")
