import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Atualizar Clientes", layout="wide")
st.markdown("## 🔄 Atualizar Lista de Clientes (clientes_status)")

# ⬇️ Conectar com a planilha Google Sheets via SECRETS
@st.cache_data(show_spinner=False)
def conectar_planilha():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        url = st.secrets["PLANILHA_URL"]["url"]
        planilha = cliente.open_by_url(url)
        return planilha
    except Exception as e:
        st.error(f"Erro ao conectar com a planilha: {e}")
        return None

# ⬇️ Carregar abas da planilha
@st.cache_data(show_spinner=False)
def carregar_abas():
    planilha = conectar_planilha()
    if planilha is None:
        return None, None
    try:
        base_dados = planilha.worksheet("Base de Dados")
        clientes_status = planilha.worksheet("clientes_status")
        return base_dados, clientes_status
    except Exception as e:
        st.error(f"Erro ao carregar abas da planilha: {e}")
        return None, None

# ⬇️ Atualizar lista de clientes mantendo Foto_URL
def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    if base_dados is None or clientes_status is None:
        return None

    dados = base_dados.get_all_records()
    df = pd.DataFrame(dados)
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    registros_atuais = clientes_status.get_all_records()
    df_atual = pd.DataFrame(registros_atuais)

    if "Cliente" not in df_atual.columns:
        df_atual["Cliente"] = []
    if "Status" not in df_atual.columns:
        df_atual["Status"] = ""
    if "Foto_URL" not in df_atual.columns:
        df_atual["Foto_URL"] = ""

    # Junta com preservação dos dados antigos
    df_novo = pd.DataFrame({"Cliente": clientes_unicos})
    df_final = df_novo.merge(df_atual, on="Cliente", how="left")

    # Garante colunas organizadas
    colunas_finais = ["Cliente", "Status", "Foto_URL"]
    for col in colunas_finais:
        if col not in df_final.columns:
            df_final[col] = ""

    df_final = df_final[colunas_finais]

    # Atualiza na planilha
    clientes_status.clear()
    clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())
    return df_final

# ⬇️ Botão para atualizar
if st.button("🔁 Atualizar Lista de Clientes"):
    with st.spinner("Atualizando lista de clientes..."):
        resultado = atualizar_clientes()
        if resultado is not None:
            st.success("✅ Lista de clientes atualizada com sucesso!")
            st.dataframe(resultado, use_container_width=True)
        else:
            st.warning("⚠️ Não foi possível atualizar a lista.")
