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

# === Interface ===
st.markdown("### 🧩 Parâmetros")
status_padrao = st.selectbox("Status padrão para novos clientes:", ["Ativo", "Inativo"])

if st.button("🔄 Atualizar Lista de Clientes"):

    def atualizar_clientes_com_status(status_inicial="Ativo"):
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
        clientes_base = sorted(df["Cliente"].dropna().unique())

        # 🔍 Recupera dados atuais da aba clientes_status
        try:
            registros_atuais = clientes_status.get_all_records()
            df_atual = pd.DataFrame(registros_atuais)
        except Exception as e:
            st.error(f"Erro ao acessar aba clientes_status: {e}")
            return None

        # 🛡️ Garante colunas mínimas
        if df_atual.empty:
            df_atual = pd.DataFrame(columns=["Cliente", "Status", "Foto"])

        df_atual["Cliente"] = df_atual["Cliente"].astype(str).str.strip()
        clientes_existentes = df_atual["Cliente"].dropna().unique()

        # ✨ Identifica novos clientes
        novos_clientes = [nome for nome in clientes_base if nome not in clientes_existentes]
        if not novos_clientes:
            st.info("Nenhum cliente novo para adicionar.")
            return df_atual

        # ➕ Cria dataframe dos novos clientes
        df_novos = pd.DataFrame({
            "Cliente": novos_clientes,
            "Status": [status_inicial] * len(novos_clientes),
            "Foto": ["" for _ in novos_clientes]
        })

        # 🧩 Junta os dados antigos com os novos
        df_final = pd.concat([df_atual, df_novos], ignore_index=True)

        # ✅ Atualiza aba
        try:
            clientes_status.clear()
            clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())
            st.success(f"{len(novos_clientes)} novo(s) cliente(s) adicionados com sucesso!")

            # 👁️ Mostrar clientes adicionados
            with st.expander("👤 Ver clientes adicionados"):
                st.dataframe(df_novos, use_container_width=True)
        except Exception as e:
            st.error(f"Erro ao atualizar a aba clientes_status: {e}")
            return None

        return df_final

    # ▶️ Executar
    resultado = atualizar_clientes_com_status(status_padrao)
    if resultado is not None:
        st.markdown("### 📋 Lista final consolidada")
        st.dataframe(resultado, use_container_width=True)
