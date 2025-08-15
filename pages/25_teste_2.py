import streamlit as st
import pandas as pd
import urllib.parse

st.set_page_config(page_title="Clientes sem Foto", page_icon="🖼", layout="wide")
st.title("🖼 Clientes sem Foto")

# CONFIG
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"  # planilha principal
ABA_STATUS = "clientes_status"  # ajuste se o nome for diferente

@st.cache_data(ttl=300)
def carregar_clientes_status():
    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(ABA_STATUS)}"
    df = pd.read_csv(url, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    return df

df_status = carregar_clientes_status()

if "Foto" not in df_status.columns:
    st.error("A coluna 'Foto' não foi encontrada na aba de clientes_status.")
else:
    sem_foto = df_status[df_status["Foto"].isna() | (df_status["Foto"].str.strip() == "")]
    if sem_foto.empty:
        st.success("✅ Todos os clientes possuem foto cadastrada.")
    else:
        st.warning(f"⚠ {len(sem_foto)} clientes sem foto cadastrada:")
        st.dataframe(sem_foto[["Cliente", "Status"]], use_container_width=True)
