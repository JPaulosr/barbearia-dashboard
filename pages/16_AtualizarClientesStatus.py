import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Atualizar Clientes", page_icon="♻️")

st.title("♻️ Atualizar clientes_status automaticamente")

# Autenticação com Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file("credenciais.json", scopes=SCOPE)
client = gspread.authorize(creds)

# Abrir planilha e abas
url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
spreadsheet = client.open_by_url(url)
aba_base = spreadsheet.worksheet("Base de Dados")
aba_clientes = spreadsheet.worksheet("clientes_status")

# Carregar dados
df_base = pd.DataFrame(aba_base.get_all_records())
df_clientes = pd.DataFrame(aba_clientes.get_all_records())

# Extrair clientes únicos da base
clientes_novos = df_base["Cliente"].dropna().unique()
clientes_atuais = df_clientes["Cliente"].dropna().unique()

# Identificar novos clientes
novos = [c for c in clientes_novos if c not in clientes_atuais]

if novos:
    st.success(f"{len(novos)} novos clientes identificados para adicionar:")
    st.write(novos)

    # Criar novas linhas
    novos_registros = [{"Cliente": nome, "Telefone": "", "Status": "Ativo", "Foto_URL": ""} for nome in novos]

    # Adicionar à planilha
    aba_clientes.append_rows([list(r.values()) for r in novos_registros])

    st.success("✅ clientes_status atualizado com sucesso!")
else:
    st.info("Nenhum cliente novo encontrado. A aba clientes_status já está atualizada.")
