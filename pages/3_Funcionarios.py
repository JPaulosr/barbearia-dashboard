import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("👨‍💼 Funcionários - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano-Mês"] = df["Data"].dt.to_period("M")
    return df

df = carregar_dados()

# Filtro por mês sincronizado com session_state
meses_disponiveis = df["Ano-Mês"].dropna().sort_values().astype(str).unique().tolist()

# Valor padrão vindo da sessão (se houver)
meses_padrao = st.session_state.get("meses", [])
mes_selecionado = st.multiselect("📅 Filtrar por mês (opcional)", meses_disponiveis, default=meses_padrao)

# Atualiza a sessão com os meses selecionados
st.session_state["meses"] = mes_selecionado

if mes_selecionado:
    df = df[df["Ano-Mês"].astype(str).isin(mes_selecionado)]

# Agrupamento por funcionário
ranking = df.groupby("Funcionário")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking["Valor Formatado"] = ranking["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.subheader("📋 Receita total por funcionário")
st.dataframe(ranking[["Funcionário", "Valor Formatado"]], use_container_width=True)

valor_total = ranking["Valor"].sum()
valor_total_formatado = f"R$ {valor_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
st.markdown(f"### 💰 Valor total no período selecionado: {valor_total_formatado}")

# Tabela com Receita por Funcionário por Mês (empilhada)
st.subheader("📊 Receita mensal por funcionário")
df["Ano-Mês"] = df["Ano-Mês"].astype(str)
df_mensal = df.groupby(["Funcionário", "Ano-Mês"])["Valor"].sum().reset_index()
df_mensal["Valor Formatado"] = df_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
tabela_pivot = df_mensal.pivot(index="Funcionário", columns="Ano-Mês", values="Valor").fillna(0)
tabela_formatada = tabela_pivot.applymap(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(tabela_formatada, use_container_width=True)

# Navegar para detalhes
funcionarios = ranking["Funcionário"].tolist()
valor_padrao = st.session_state.get("funcionario", "Selecione...")
opcoes = ["Selecione..."] + funcionarios

try:
    index_padrao = opcoes.index(valor_padrao)
except ValueError:
    index_padrao = 0

filtro = st.selectbox("🔍 Ver detalhamento de um funcionário", opcoes, index=index_padrao)

if st.button("➞ Ver detalhes"):
    if filtro != "Selecione...":
        st.session_state["funcionario"] = filtro
        st.rerun()
    else:
        st.warning("Por favor, selecione um funcionário válido.")

if "funcionario" in st.session_state and st.session_state["funcionario"] != "Selecione...":
    st.switch_page("pages/4_DetalhesFuncionario.py")
