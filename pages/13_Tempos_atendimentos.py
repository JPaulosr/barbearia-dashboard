import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")
st.title("🗓️ Frequência dos Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

df = carregar_dados()

# === Filtro de funcionario ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios_selecionados = st.multiselect("👨‍💼 Filtrar por funcionário", funcionarios, default=funcionarios)

if funcionarios_selecionados:
    df = df[df["Funcionário"].isin(funcionarios_selecionados)]

# === Processar frequência ===
hoje = pd.to_datetime(datetime.now().date())
frequencia_clientes = []

for cliente, grupo in df.groupby("Cliente"):
    datas = grupo.sort_values("Data")["Data"].tolist()
    if len(datas) >= 2:
        diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
        freq_media = sum(diffs) / len(diffs)
    else:
        freq_media = None

    ultima_data = datas[-1]
    dias_sem_cortar = (hoje - ultima_data).days

    # Status
    if freq_media:
        if dias_sem_cortar <= freq_media:
            status = "🟢 Em dia"
        elif dias_sem_cortar <= freq_media + 5:
            status = "🟠 Pouco atrasado"
        else:
            status = "🔴 Atrasado"
    else:
        status = "❓ Sem histórico"

    frequencia_clientes.append({
        "Cliente": cliente,
        "Data do Último Atendimento": ultima_data.date(),
        "Dias desde o Último": dias_sem_cortar,
        "Frequência Média (dias)": round(freq_media, 1) if freq_media else "-",
        "Status": status
    })

resumo_df = pd.DataFrame(frequencia_clientes)

# === Filtro por status ===
status_opcoes = resumo_df["Status"].unique().tolist()
status_selecionados = st.multiselect("⚠️ Filtrar por status", status_opcoes, default=status_opcoes)

resumo_df = resumo_df[resumo_df["Status"].isin(status_selecionados)]

# === Mostrar tabela ===
st.dataframe(resumo_df.sort_values("Dias desde o Último", ascending=False), use_container_width=True)

# === Exportar CSV ===
st.download_button(
    label="📂 Baixar como CSV",
    data=resumo_df.to_csv(index=False).encode("utf-8"),
    file_name="frequencia_clientes.csv",
    mime="text/csv"
)
