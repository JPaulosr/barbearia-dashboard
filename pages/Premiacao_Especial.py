import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🎉 Premiação Especial - Destaques do Ano")

# === Conectar e carregar dados ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

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
    aba = planilha.worksheet("Base de Dados")
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

df = carregar_dados()

# === Funções auxiliares ===
def limpar_nomes(nome):
    nome = str(nome).strip().lower()
    nomes_excluir = ["boliviano", "brasileiro", "menino", "sem nome", "cliente", "sem preferência", "sem preferencia"]
    return not any(gen in nome for gen in nomes_excluir)

df = df[df["Cliente"].notna()]
df = df[df["Cliente"].apply(limpar_nomes)]
df = df[df["Valor"] > 0]

# === Cliente Mais Fiel ===
st.subheader("🎯 Cliente Mais Fiel")
clientes_fieis = df.groupby("Cliente")["Data"].apply(lambda x: x.dt.to_period("M").nunique()).sort_values(ascending=False).head(1)
for cliente, meses in clientes_fieis.items():
    st.markdown(f"🏅 **{cliente.title()}** participou em **{meses} meses diferentes**!")

# === Cliente Combo ===
st.subheader("🧼 Cliente Combo")
df_combo = df.copy()
df_combo["Dia"] = df_combo["Data"].dt.date
combos = df_combo.groupby(["Cliente", "Dia"]).size().reset_index(name="Qtd")
combos = combos[combos["Qtd"] > 1]
combo_count = combos.groupby("Cliente")["Dia"].count().sort_values(ascending=False).head(1)
for cliente, qtd in combo_count.items():
    st.markdown(f"🏅 **{cliente.title()}** fez **{qtd} atendimentos com combos**!")

# === Cliente Frequente ===
st.subheader("📅 Cliente Mais Frequente")
freq_resultados = []
for nome, grupo in df.groupby("Cliente"):
    datas = sorted(grupo["Data"].drop_duplicates())
    if len(datas) >= 2:
        intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, len(datas))]
        media_dias = sum(intervalos) / len(intervalos)
        freq_resultados.append((nome, media_dias))
df_freq = pd.DataFrame(freq_resultados, columns=["Cliente", "Frequência Média"]).sort_values("Frequência Média").head(1)
for _, row in df_freq.iterrows():
    st.markdown(f"🏅 **{row['Cliente'].title()}** retornava em média a cada **{row['Frequência Média']:.1f} dias**!")
