import streamlit as st
import pandas as pd

st.set_page_config(page_title="Atualizar Clientes", page_icon="♻️")
st.title("♻️ Atualizar clientes_status automaticamente")

# Links diretos para o CSV da planilha
url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
url_status = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=clientes_status"

# Carregar as abas
df_base = pd.read_csv(url_base)
df_status = pd.read_csv(url_status)

# Garantir que as colunas necessárias existem
if "Cliente" not in df_base.columns or "Cliente" not in df_status.columns:
    st.error("⚠️ A coluna 'Cliente' não foi encontrada em uma das abas. Verifique os cabeçalhos.")
    st.stop()

# Limpeza e comparação
clientes_base = df_base["Cliente"].dropna().str.strip().unique()
clientes_status = df_status["Cliente"].dropna().str.strip().unique()

novos = [c for c in clientes_base if c not in clientes_status]

if novos:
    st.success(f"{len(novos)} novos clientes encontrados:")
    st.write(novos)
    st.warning("⚠️ Atualização automática da planilha requer permissão de escrita (gspread).")
    st.info("Copie e cole manualmente os nomes abaixo na aba 'clientes_status', ou ative autenticação via `credenciais.json` para automatizar.")
else:
    st.info("✅ Nenhum novo cliente encontrado. Tudo atualizado.")
