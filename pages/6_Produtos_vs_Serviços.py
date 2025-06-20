import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("📦 Produtos vs Serviços")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# === FILTROS ===
anos = sorted(df["Ano"].dropna().unique())
ano = st.selectbox("📅 Selecione o ano", anos)

df_ano = df[df["Ano"] == ano]

meses_nome = {
    1:"Jan", 2:"Fev", 3:"Mar", 4:"Abr", 5:"Mai", 6:"Jun",
    7:"Jul", 8:"Ago", 9:"Set", 10:"Out", 11:"Nov", 12:"Dez"
}
meses_opcoes = sorted(df_ano["Mês"].dropna().unique())
meses_default = meses_opcoes if len(meses_opcoes) <= 6 else meses_opcoes[-3:]
meses_selecionados = st.multiselect("📆 Filtrar por mês (opcional)", options=[meses_nome[m] for m in meses_opcoes], default=[meses_nome[m] for m in meses_default])
meses_valores = [k for k,v in meses_nome.items() if v in meses_selecionados]

df_filtrado = df_ano[df_ano["Mês"].isin(meses_valores)] if meses_selecionados else df_ano

# === SEPARAÇÃO POR TIPO ===
df_serv = df_filtrado[df_filtrado["Tipo"].str.lower() == "serviço"]
df_prod = df_filtrado[df_filtrado["Tipo"].str.lower() == "produto"]

# === TABELAS ===
st.subheader("💈 Receita por tipo de **serviço**")
tabela_serv = df_serv.groupby("Serviço")["Valor"].sum().reset_index(name="Receita")
tabela_serv = tabela_serv.sort_values(by="Receita", ascending=False)
tabela_serv["Receita Formatada"] = tabela_serv["Receita"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(tabela_serv[["Serviço", "Receita Formatada"]], use_container_width=True)

st.subheader("🛍️ Receita por tipo de **produto**")
tabela_prod = df_prod.groupby("Serviço")["Valor"].sum().reset_index(name="Receita")
tabela_prod = tabela_prod.sort_values(by="Receita", ascending=False)
tabela_prod["Receita Formatada"] = tabela_prod["Receita"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(tabela_prod[["Serviço", "Receita Formatada"]], use_container_width=True)

# === TOTALIZADOR FINAL ===
total_serv = tabela_serv["Receita"].sum()
total_prod = tabela_prod["Receita"].sum()
total_geral = total_serv + total_prod

st.markdown("### 📊 Totais gerais")
col1, col2, col3 = st.columns(3)
col1.metric("💈 Total em Serviços", f"R$ {total_serv:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("🛍️ Total em Produtos", f"R$ {total_prod:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("📦 Total Geral", f"R$ {total_geral:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
