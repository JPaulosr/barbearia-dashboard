import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import datetime
import io

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# === CONFIGURAÇÕES ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
PASTA_ID_DRIVE = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# === AUTENTICAÇÃO GOOGLE ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID), credenciais

@st.cache_data
def carregar_dados():
    planilha, _ = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    if "Duração (min)" not in df.columns or df["Duração (min)"].isna().all():
        if set(["Hora Chegada", "Hora Saída do Salão"]).issubset(df.columns):
            def calcular_duracao(row):
                try:
                    h1 = pd.to_datetime(row["Hora Chegada"], format="%H:%M:%S")
                    h2 = pd.to_datetime(row["Hora Saída do Salão"], format="%H:%M:%S")
                    return (h2 - h1).total_seconds() / 60 if h2 > h1 else None
                except:
                    return None
            df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

df = carregar_dados()
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === EXIBIR FOTO DO CLIENTE ===
try:
    if "Foto_URL" in df.columns:
        df_foto = df[df["Cliente"] == cliente]
        url_foto = df_foto["Foto_URL"].dropna().unique()
        if len(url_foto) > 0:
            link = url_foto[0]
            if "drive.google.com" in link and "/file/d/" in link:
                file_id = link.split("/file/d/")[1].split("/")[0]
                link = f"https://drive.google.com/uc?id={file_id}"
            st.image(link, width=200, caption=f"Foto de {cliente}")
        else:
            st.info(f"ℹ️ Nenhuma imagem cadastrada para **{cliente}**.")
    else:
        st.info("ℹ️ A coluna 'Foto_URL' ainda não existe na planilha.")
except Exception as e:
    st.warning(f"Erro ao carregar foto: {e}")

# === UPLOAD PARA GOOGLE DRIVE ===
with st.expander("📤 Enviar nova foto do cliente para o Google Drive"):
    uploaded = st.file_uploader("Escolha uma imagem", type=["jpg", "jpeg", "png"])
    if uploaded:
        st.image(uploaded, width=200)
        if st.button("Salvar imagem no Google Drive e atualizar planilha"):
            _, creds = conectar_sheets()
            service = build("drive", "v3", credentials=creds)

            media = MediaIoBaseUpload(uploaded, mimetype=uploaded.type, resumable=True)
            nome_arquivo = f"{cliente}.jpg"

            file_metadata = {
                "name": nome_arquivo,
                "parents": [PASTA_ID_DRIVE]
            }

            arquivo = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()

            file_id = arquivo.get("id")
            link_final = f"https://drive.google.com/uc?id={file_id}"
            st.success("✅ Imagem enviada com sucesso!")
            st.write("🔗 Link da imagem:", link_final)

            # Atualizar planilha
            planilha, _ = conectar_sheets()
            aba = planilha.worksheet(BASE_ABA)
            registros = aba.get_all_records()
            for i, row in enumerate(registros):
                if row.get("Cliente", "").strip().lower() == cliente.strip().lower():
                    aba.update_cell(i + 2, 14, link_final)  # coluna N = 14
                    st.success("📄 Planilha atualizada com novo link da imagem.")
                    break
