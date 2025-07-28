import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def carregar_dados_existentes():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba

def salvar_atendimento(novo_df):
    df_existente, aba = carregar_dados_existentes()
    df_atualizado = pd.concat([df_existente, novo_df], ignore_index=True)
    set_with_dataframe(aba, df_atualizado)

# === FORMULÁRIO DE ATENDIMENTO ===
st.title("✍️ Adicionar Atendimento Manual")

with st.form("formulario_atendimento"):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        servico = st.text_input("Serviço")
        valor = st.number_input("Valor (R$)", min_value=0.0, step=0.5, format="%.2f")
        conta = st.selectbox("Conta", ["Carteira", "Nubank"])
        cliente = st.text_input("Nome do Cliente")
        combo = st.text_input("Combo (deixe vazio se não for combo)")
    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        fase = st.selectbox("Fase", ["Autônomo (prestador)", "Dono (sozinho)", "Dono + funcionário"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        hora_chegada = st.time_input("Hora de Chegada")
        hora_inicio = st.time_input("Hora de Início")
        hora_saida = st.time_input("Hora de Saída")
        hora_saida_salao = st.time_input("Hora Saída do Salão", disabled=True)  # pode deixar opcional

    enviar = st.form_submit_button("💾 Salvar Atendimento")

if enviar:
    if not cliente or not servico:
        st.error("❗ Nome do cliente e serviço são obrigatórios.")
    else:
        novo = pd.DataFrame([{
            "Data": data.strftime("%d/%m/%Y"),
            "Serviço": servico.strip(),
            "Valor": f"R$ {valor:.2f}",
            "Conta": conta,
            "Cliente": cliente.strip(),
            "Combo": combo.strip(),
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": hora_chegada.strftime("%H:%M:%S"),
            "Hora Início": hora_inicio.strftime("%H:%M:%S"),
            "Hora Saída": hora_saida.strftime("%H:%M:%S"),
            "Hora Saída do Salão": ""  # opcional
        }])

        salvar_atendimento(novo)
        st.success("✅ Atendimento registrado com sucesso!")
