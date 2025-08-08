import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Criar coluna Período", page_icon="🕒", layout="wide")
st.title("🕒 Criar coluna 'Período' (Manhã/Tarde/Noite) a partir dos horários")

# === 1) Carregar Base do Google Sheets (CSV público) ===
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    # Tipos básicos
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date

    # Converter colunas de horário para datetime (mantém NaT se vazio)
    for col in ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    return df

df = carregar_dados_google_sheets()

# Validação mínima (só para garantir que as colunas existem)
colunas_necessarias = ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"]
faltando = [c for c in colunas_necessarias if c not in df.columns]
if faltando:
    st.error(f"Colunas de horário ausentes na base: {', '.join(faltando)}")
    st.stop()

st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

# === 2) (BLOCO QUE VOCÊ PODE COPIAR PARA O SEU APP) Criar coluna 'Período' ===
# Prioridade: Hora Início > Hora Chegada > Hora Saída > Hora Saída do Salão
def definir_periodo(horario):
    if pd.isna(horario):
        return "Indefinido"
    h = int(horario.hour)
    if 6 <= h < 12:
        return "Manhã"
    elif 12 <= h < 18:
        return "Tarde"
    else:
        return "Noite"

def primeiro_horario_valido(row):
    for c in ["Hora Início", "Hora Chegada", "Hora Saída", "Hora Saída do Salão"]:
        if c in row and pd.notna(row[c]):
            return row[c]
    return pd.NaT

df["Período"] = df.apply(lambda r: definir_periodo(primeiro_horario_valido(r)), axis=1)

st.success("Coluna 'Período' criada com sucesso a partir dos horários existentes.")

# === 3) Prévia e Download ===
st.subheader("Prévia (com a nova coluna 'Período')")
cols_preview = [c for c in ["Data","Cliente","Funcionário","Tipo","Combo","Hora Chegada","Hora Início","Hora Saída","Hora Saída do Salão","Período"] if c in df.columns]
st.dataframe(df[cols_preview].head(50), use_container_width=True)

csv_out = df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="⬇️ Baixar CSV com a coluna 'Período'",
    data=csv_out,
    file_name="base_com_periodo.csv",
    mime="text/csv"
)

st.caption("Obs.: Este app não altera sua planilha. Ele só cria a coluna em memória e permite baixar o CSV atualizado.")
