import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")
st.title("🛠️ Gestão de Clientes")

# === Carrega base de dados principal ===
@st.cache_data

def carregar_base():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [col.strip() for col in df.columns]
    return df

df = carregar_base()

# === Caminho do arquivo de status ===
caminho_status = "clientes_status.csv"

# === Garante que o arquivo de status exista ===
if not os.path.exists(caminho_status):
    clientes_unicos = sorted(df["Cliente"].dropna().unique())
    df_status_inicial = pd.DataFrame({"Cliente": clientes_unicos, "Status": ["Ativo"] * len(clientes_unicos)})
    df_status_inicial.to_csv(caminho_status, index=False)

# === Carrega status atual ===
df_status = pd.read_csv(caminho_status)

# === Atualiza lista de clientes se houver novos ===
clientes_novos = set(df["Cliente"].dropna().unique()) - set(df_status["Cliente"])
if clientes_novos:
    novos = pd.DataFrame({"Cliente": list(clientes_novos), "Status": ["Ativo"] * len(clientes_novos)})
    df_status = pd.concat([df_status, novos], ignore_index=True)
    df_status.to_csv(caminho_status, index=False)

# === Interface de edição ===
st.subheader("📃 Lista de Clientes com Status")

status_opcoes = ["Ativo", "Inativo", "Ignorado"]

clientes = df_status.sort_values("Cliente").reset_index(drop=True)

for i, row in clientes.iterrows():
    col1, col2 = st.columns([4, 2])
    col1.markdown(f"**{row['Cliente']}**")
    novo_status = col2.selectbox("", status_opcoes, index=status_opcoes.index(row["Status"]), key=f"status_{i}")
    df_status.at[i, "Status"] = novo_status

# === Botão de salvar ===
if st.button("💾 Salvar alterações"):
    df_status.to_csv(caminho_status, index=False)
    st.success("Status dos clientes atualizado com sucesso!")
