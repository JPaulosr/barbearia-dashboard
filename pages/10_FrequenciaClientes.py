import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📆 Frequência dos Clientes")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

df = carregar_dados()
hoje = pd.to_datetime(datetime.today().date())

clientes = df["Cliente"].dropna().unique()
resumo_lista = []

for cliente in clientes:
    df_cliente = df[df["Cliente"] == cliente].sort_values("Data")
    datas = df_cliente["Data"].tolist()

    if len(datas) < 2:
        freq_media = None
    else:
        intervalos = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
        freq_media = round(sum(intervalos) / len(intervalos), 1)

    ultima_data = datas[-1]
    dias_sem_cortar = (hoje - ultima_data).days

    if freq_media:
        if dias_sem_cortar <= freq_media:
            status = "✔️ Em dia"
        elif dias_sem_cortar <= freq_media + 5:
            status = "⚠️ Pouco atrasado"
        else:
            status = "❌ Atrasado"
    else:
        status = "-"

    resumo_lista.append({
        "Cliente": cliente,
        "Último Atendimento": ultima_data.date(),
        "Dias sem cortar": dias_sem_cortar,
        "Frequência Média (dias)": freq_media if freq_media else "-",
        "Status": status
    })

resumo_df = pd.DataFrame(resumo_lista)
resumo_df = resumo_df.sort_values(by="Dias sem cortar", ascending=False)

st.dataframe(resumo_df, use_container_width=True)
st.caption("Clientes com base no intervalo entre os últimos atendimentos")
