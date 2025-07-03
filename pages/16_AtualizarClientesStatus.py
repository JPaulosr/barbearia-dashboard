import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time

st.set_page_config(page_title="Atualizar clientes_status", page_icon="♻️", layout="wide")
st.title("♻️ Atualizar clientes_status automaticamente")

# ====================
# Autenticação com Google Sheets via credenciais.json
# ====================
SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"  # ID da sua planilha
SHEET_NAME_BASE = "Base de Dados"
SHEET_NAME_STATUS = "clientes_status"

try:
    creds = Credentials.from_service_account_file("credenciais.json", scopes=SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    aba_base = sheet.worksheet(SHEET_NAME_BASE)
    aba_status = sheet.worksheet(SHEET_NAME_STATUS)
except Exception as e:
    st.error(f"Erro ao autenticar ou acessar planilhas: {e}")
    st.stop()

# ====================
# Coletar todos os nomes únicos da Base de Dados
# ====================
try:
    dados_base = pd.DataFrame(aba_base.get_all_records())
    dados_base["Cliente"] = dados_base["Cliente"].astype(str).str.strip().str.lower()
    nomes_unicos = sorted(dados_base["Cliente"].dropna().unique())
except Exception as e:
    st.error(f"Erro ao ler a base de dados: {e}")
    st.stop()

# ====================
# Carregar os clientes já presentes em clientes_status
# ====================
try:
    dados_status = pd.DataFrame(aba_status.get_all_records())
    nomes_existentes = dados_status.iloc[:, 0].astype(str).str.strip().str.lower().tolist()
except:
    dados_status = pd.DataFrame()
    nomes_existentes = []

# ====================
# Identificar novos clientes
# ====================
novos_clientes = [nome for nome in nomes_unicos if nome not in nomes_existentes]

st.success(f"{len(novos_clientes)} novos clientes encontrados:")
with st.expander("🔍 Ver nomes dos novos clientes"):
    for i in range(0, len(novos_clientes), 100):
        st.write(f"[ {i} – {min(i+100, len(novos_clientes))} ]")
        st.code("\n".join(novos_clientes[i:i+100]))

# ====================
# Botão para atualizar planilha automaticamente
# ====================
if len(novos_clientes) > 0:
    if st.button("✍️ Atualizar automaticamente aba 'clientes_status'"):
        try:
            novos_registros = [[nome.title(), "Ativo"] for nome in novos_clientes]
            aba_status.append_rows(novos_registros)
            st.success(f"✅ {len(novos_clientes)} novos clientes adicionados com sucesso à aba 'clientes_status'!")
        except Exception as e:
            st.error(f"Erro ao atualizar a aba clientes_status: {e}")
else:
    st.info("Nenhum novo cliente para adicionar.")
