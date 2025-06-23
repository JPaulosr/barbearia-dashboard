import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Top 20 Clientes", layout="wide")

st.markdown("## 🏅 Top 20 Clientes - Geral")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [col.strip() for col in df.columns]
    df = df[['Data', 'Valor', 'Cliente', 'Funcionário']].dropna()

    df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    df['Valor'] = df['Valor'].astype(str).str.replace("R$", "").str.replace(",", ".").str.strip()
    df['Valor'] = pd.to_numeric(df['Valor'], errors='coerce')

    # Remove nomes genéricos
    nomes_excluir = ['boliviano', 'brasileiro', 'menino']
    df = df[~df['Cliente'].str.lower().isin(nomes_excluir)]

    return df

df = carregar_dados()

# Filtros
ano = st.selectbox("📅 Filtrar por ano", options=sorted(df['Data'].dt.year.unique(), reverse=True))
funcionarios = st.multiselect("👨‍🔧 Filtrar por funcionário", options=sorted(df['Funcionário'].dropna().unique()), default=sorted(df['Funcionário'].dropna().unique()))

df = df[(df['Data'].dt.year == ano) & (df['Funcionário'].isin(funcionarios))]

if df.empty:
    st.warning("Nenhum dado encontrado com os filtros aplicados.")
    st.stop()

# Separar antes e depois de 11/05/2025
data_corte = pd.to_datetime("2025-05-11")
df_antes = df[df['Data'] < data_corte].copy()
df_depois = df[df['Data'] >= data_corte].copy()

# Antes de 11/05: cada linha é 1 atendimento
df_antes['Qtd_Atendimentos'] = 1
agrupado_antes = df_antes.groupby('Cliente').agg(
    Qtd_Atendimentos=('Qtd_Atendimentos', 'sum'),
    Valor_Total=('Valor', 'sum')
).reset_index()

# Depois de 11/05: agrupa por Cliente + Data
agrupado_depois = df_depois.groupby(['Cliente', 'Data']).agg(
    Valor_Dia=('Valor', 'sum')
).reset_index()

agrupado_final = agrupado_depois.groupby('Cliente').agg(
    Qtd_Atendimentos=('Data', 'nunique'),
    Valor_Total=('Valor_Dia', 'sum')
).reset_index()

# Junta os dois blocos
df_top = pd.concat([agrupado_antes, agrupado_final], ignore_index=True)
df_top = df_top.groupby('Cliente').agg(
    Qtd_Atendimentos=('Qtd_Atendimentos', 'sum'),
    Valor_Total=('Valor_Total', 'sum')
).reset_index()

# Formatação final
df_top['Valor_Formatado'] = df_top['Valor_Total'].apply(lambda x: f"R$ {x:,.2f}".replace('.', ','))
df_top = df_top.sort_values(by='Valor_Total', ascending=False).reset_index(drop=True)
df_top['Posição'] = np.arange(1, len(df_top) + 1)
df_top = df_top[['Posição', 'Cliente', 'Qtd_Atendimentos', 'Valor_Total', 'Valor_Formatado']]

# Exibe ranking
st.dataframe(df_top.head(20), use_container_width=True)

# Filtro por nome
st.markdown("### 🔍 Pesquisar cliente")
nome_busca = st.text_input("Digite um nome (ou parte dele)")
if nome_busca:
    resultado = df_top[df_top['Cliente'].str.lower().str.contains(nome_busca.lower())]
    st.dataframe(resultado, use_container_width=True)
