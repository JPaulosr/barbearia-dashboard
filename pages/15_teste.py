import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime
import re

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

# === CORRIGIR LINKS DA COLUNA Foto_URL ===
def corrigir_links_foto_url():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    coluna_foto_url = aba.col_values(14)
    novos_links = []
    alterados = 0

    for url in coluna_foto_url:
        if "drive.google.com" in url and "/file/d/" in url:
            try:
                file_id = re.search(r"/file/d/([a-zA-Z0-9_-]+)", url).group(1)
                novo_url = f"https://drive.google.com/uc?id={file_id}"
                novos_links.append(novo_url)
                alterados += 1
            except:
                novos_links.append(url)
        else:
            novos_links.append(url)

    # Atualiza a partir da célula N2 (ignora cabeçalho)
    celulas = aba.range(f"N2:N{len(novos_links)+1}")
    for i, cell in enumerate(celulas):
        cell.value = novos_links[i]
    aba.update_cells(celulas)

    return alterados

# === BOTÃO DE CORREÇÃO ===
with st.expander("🛠️ Corrigir links da coluna Foto_URL"):
    if st.button("🔄 Corrigir agora"):
        total = corrigir_links_foto_url()
        st.success(f"✅ {total} link(s) corrigido(s) com sucesso!")

# === DADOS E SELEÇÃO ===
df = carregar_dados()
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === FOTO DO CLIENTE ===
try:
    if "Foto_URL" in df.columns:
        df_foto = df[df["Cliente"] == cliente]
        url_foto = df_foto["Foto_URL"].dropna().unique()
        if len(url_foto) > 0:
            link = url_foto[0]
            if "drive.google.com" in link and "/file/d/" in link:
                file_id = link.split("/file/d/")[1].split("/")[0]
                link = f"https://drive.google.com/uc?id={file_id}"
            st.image(link, width=150, caption=f"Foto de {cliente}")
        else:
            st.info(f"ℹ️ Nenhuma imagem cadastrada para **{cliente}**.")
    else:
        st.info("ℹ️ A coluna 'Foto_URL' ainda não existe na planilha.")
except Exception as e:
    st.warning(f"Erro ao carregar foto: {e}")
