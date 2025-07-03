import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="🔧 Correção de Cabeçalho", layout="centered")
st.title("🛠️ Corrigir Cabeçalho da Aba clientes_status")

# === CONFIGURAÇÕES ===
planilha_id = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
aba_nome = "clientes_status"

# Autenticação com Google
@st.cache_resource
def autenticar_gspread():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopos = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credenciais = Credentials.from_service_account_info(info, scopes=escopos)
    return gspread.authorize(credenciais)

gc = autenticar_gspread()

# Cabeçalhos corretos (ajuste conforme sua aba clientes_status real)
cabecalhos_corrigidos = ["Cliente", "Telefone", "Status", "Foto_URL"]

# === Execução ===
if st.button("⚠️ Corrigir Cabeçalho da Aba"):
    try:
        aba = gc.open_by_key(planilha_id).worksheet(aba_nome)

        # Pega dados existentes
        dados_existentes = aba.get_all_values()[1:]  # ignora cabeçalho antigo

        # Apaga tudo e reescreve
        aba.clear()
        aba.append_row(cabecalhos_corrigidos)

        # Restaura dados existentes (sem cabeçalho)
        for linha in dados_existentes:
            if any(campo.strip() for campo in linha):
                aba.append_row(linha[:len(cabecalhos_corrigidos)])

        st.success("✅ Cabeçalho corrigido com sucesso!")
    except Exception as e:
        st.error(f"❌ Erro ao corrigir cabeçalho: {e}")
else:
    st.info("Clique no botão acima para reescrever o cabeçalho da aba `clientes_status`.")
