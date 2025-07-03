import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime
import requests

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
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

# === UPLOAD DE IMAGEM ===
with st.expander("📤 Enviar nova foto do cliente"):
    uploaded = st.file_uploader("Escolha uma imagem", type=["jpg", "png", "jpeg"])
    if uploaded:
        st.image(uploaded, width=200)
        if st.button("Salvar imagem no Imgur e atualizar planilha"):
            client_id = st.secrets["IMGUR"]["client_id"]
            headers = {"Authorization": f"Client-ID {client_id}"}
            files = {"image": uploaded.getvalue()}
            response = requests.post("https://api.imgur.com/3/image", headers=headers, files=files)

            if response.status_code == 200:
                img_url = response.json()["data"]["link"]
                st.success("Imagem enviada com sucesso!")
                st.write("Link gerado:", img_url)

                # Atualizar a planilha com novo link
                planilha = conectar_sheets()
                aba = planilha.worksheet(BASE_ABA)
                registros = aba.get_all_records()
                for i, row in enumerate(registros):
                    if row.get("Cliente", "").strip().lower() == cliente.strip().lower():
                        aba.update_cell(i + 2, 14, img_url)  # Coluna N (14ª)
                        st.success("Planilha atualizada com a nova imagem.")
                        break
            else:
                st.error("Erro ao enviar imagem para o Imgur.")

# (continua normalmente com o restante do seu código abaixo)
