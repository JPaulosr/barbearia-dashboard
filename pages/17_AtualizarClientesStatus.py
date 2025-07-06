import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📌 Atualizar Lista de Clientes (clientes_status)")

# === Conectar ao Google Sheets ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def conectar_sheets():
    credenciais = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=SCOPES)
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(SHEET_ID)
    return planilha

def carregar_abas():
    try:
        planilha = conectar_sheets()
        base_dados = planilha.worksheet("Base de Dados")
        clientes_status = planilha.worksheet("clientes_status")
        return base_dados, clientes_status
    except Exception as e:
        st.error(f"Erro ao carregar planilhas: {e}")
        return None, None

def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    if base_dados is None or clientes_status is None:
        return None

    # 🔄 Carrega a aba "Base de Dados"
    try:
        dados = base_dados.get_all_values()
        df = pd.DataFrame(dados[1:], columns=dados[0])  # pula cabeçalho
    except Exception as e:
        st.error(f"Erro ao carregar dados da planilha: {e}")
        return None

    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    # 🔍 Recupera dados atuais da aba clientes_status
    try:
        registros_atuais = clientes_status.get_all_records()
        df_atual = pd.DataFrame(registros_atuais)
    except Exception as e:
        st.error(f"Erro ao acessar aba clientes_status: {e}")
        return None

    # 🛡️ Garante colunas mínimas
    if "Cliente" not in df_atual.columns:
        df_atual["Cliente"] = []
    if "Status" not in df_atual.columns:
        df_atual["Status"] = ""
    if "Foto" not in df_atual.columns:
        df_atual["Foto"] = ""

    # 🔗 Junta novos clientes com existentes (sem apagar links e status)
    df_novo = pd.DataFrame({"Cliente": clientes_unicos})
    df_final = df_novo.merge(df_atual, on="Cliente", how="left")

    # 📋 Reorganiza colunas obrigatórias
    colunas = ["Cliente", "Status", "Foto"]
    for col in colunas:
        if col not in df_final.columns:
            df_final[col] = ""
    df_final = df_final[colunas]

    # 🧹 Limpa e atualiza aba com a nova lista
    try:
        clientes_status.clear()
        clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())
        st.success("Lista de clientes atualizada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao atualizar a aba clientes_status: {e}")
        return None

    return df_final

# === Interface Streamlit ===
if st.button("🔄 Atualizar Lista de Clientes"):
    resultado = atualizar_clientes()
    if resultado is not None:
        st.dataframe(resultado, use_container_width=True)
