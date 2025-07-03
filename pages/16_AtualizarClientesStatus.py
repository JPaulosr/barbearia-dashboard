import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import time

st.set_page_config(page_title="Atualizar Clientes Status", layout="wide")
st.title("♻️ Atualizar clientes_status automaticamente")

# Função para carregar dados da planilha
@st.cache_data
def carregar_dados():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    url_status = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=clientes_status"
    df_base = pd.read_csv(url_base)
    df_status = pd.read_csv(url_status)
    return df_base, df_status

# Carregar dados
df_base, df_status = carregar_dados()

# Clientes únicos na base de dados
clientes_base = sorted(df_base["Cliente"].dropna().unique())

# Clientes já existentes na aba clientes_status
clientes_status = sorted(df_status["Cliente"].dropna().unique())

# Identificar novos clientes ainda não cadastrados
clientes_novos = sorted(set(clientes_base) - set(clientes_status))

st.success(f"{len(clientes_novos)} novos clientes encontrados:")

# Quebra em grupos de 100
for i in range(0, len(clientes_novos), 100):
    st.markdown(f"<details><summary>[ {i} – {min(i+100, len(clientes_novos))} ]</summary><p>", unsafe_allow_html=True)
    for cliente in clientes_novos[i:i+100]:
        st.text(cliente)
    st.markdown("</p></details>", unsafe_allow_html=True)

# Botão para atualizar a planilha diretamente
st.warning("⚠️ Atualização automática da planilha requer permissão de escrita (gspread).")

# Upload do arquivo de credenciais
arquivo_credenciais = st.file_uploader("📄 Envie seu arquivo `credenciais.json` para autenticar com o Google", type="json")

if arquivo_credenciais is not None:
    try:
        # Autenticar com as credenciais
        credentials = Credentials.from_service_account_info(
            info=pd.read_json(arquivo_credenciais, typ='series').to_dict(),
            scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )

        client = gspread.authorize(credentials)
        sheet = client.open_by_key("1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE")
        aba = sheet.worksheet("clientes_status")

        # Inserir novos clientes na próxima linha
        valores_novos = [[nome] for nome in clientes_novos]
        aba.append_rows(valores_novos, value_input_option="RAW")

        st.success("✅ Planilha atualizada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao autenticar ou atualizar a planilha: {e}")
else:
    st.info("Copie e cole manualmente os nomes abaixo na aba 'clientes_status', ou envie o arquivo de credenciais acima para automatizar.")
