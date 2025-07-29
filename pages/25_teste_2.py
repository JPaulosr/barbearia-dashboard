import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import re

st.set_page_config(page_title="Adicionar Atendimento", page_icon="📝", layout="wide")
st.markdown("# 🖊️ Adicionar Atendimento Manual")

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

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba

def salvar_novos_dados(novos_registros):
    df, aba = carregar_base()
    df_final = pd.concat([df, novos_registros], ignore_index=True)
    aba.clear()
    set_with_dataframe(aba, df_final)

# === Carregar base para preenchimento automático ===
df_base, _ = carregar_base()
servicos_disponiveis = sorted(df_base["Serviço"].dropna().unique())
formas_pagamento = sorted(df_base["Conta"].dropna().unique())
clientes_cadastrados = sorted(df_base["Cliente"].dropna().unique())
combos_registrados = sorted(df_base["Combo"].dropna().unique())

# === FORMULÁRIO ===
with st.form("form_atendimento"):
    col1, col2 = st.columns(2)

    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        conta = st.selectbox("Forma de Pagamento", formas_pagamento)
        cliente = st.text_input("Nome do Cliente", placeholder="Digite o nome do cliente").strip()
        combo = st.selectbox("Combo (opcional - use 'corte+barba')", [""] + combos_registrados)

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        chegada = st.time_input("Hora de Chegada (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        inicio = st.time_input("Hora de Início (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        saida = st.time_input("Hora de Saída (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        saida_salao = st.time_input("Hora Saída do Salão (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())

    # Atendimento simples (se combo estiver vazio)
    if not combo:
        servico = st.selectbox("Serviço", servicos_disponiveis)
        valor_padrao = df_base[df_base["Serviço"] == servico]["Valor"].dropna().iloc[-1] if not df_base[df_base["Serviço"] == servico].empty else 0
        valor = st.text_input(f"Valor do serviço: {servico}", value=f"{valor_padrao:.2f}".replace(".", ","))

    st.markdown("")

    salvar = st.form_submit_button("📄 Salvar Atendimento")

if salvar:
    if not cliente:
        st.warning("⚠️ Informe o nome do cliente.")
        st.stop()

    fase = "Dono + funcionário"
    registros = []

    if combo:
        servicos = [s.strip() for s in combo.split("+") if s.strip()]
        for idx, serv in enumerate(servicos):
            valor_ref = df_base[df_base["Serviço"].str.lower() == serv.lower()]["Valor"].dropna()
            valor_usado = valor_ref.iloc[-1] if not valor_ref.empty else 0
            novo_registro = {
                "Data": data.strftime("%d/%m/%Y"),
                "Serviço": serv,
                "Valor": f"R$ {valor_usado:.2f}".replace(".", ","),
                "Conta": conta,
                "Cliente": cliente,
                "Combo": combo,
                "Funcionário": funcionario,
                "Fase": fase,
                "Tipo": tipo,
                "Hora Chegada": chegada.strftime("%H:%M:%S") if idx == 0 else "00:00:00",
                "Hora Início": inicio.strftime("%H:%M:%S") if idx == 0 else "00:00:00",
                "Hora Saída": saida.strftime("%H:%M:%S") if idx == 0 else "00:00:00",
                "Hora Saída do Salão": saida_salao.strftime("%H:%M:%S") if idx == 0 else "00:00:00"
            }
            registros.append(novo_registro)
    else:
        novo_registro = {
            "Data": data.strftime("%d/%m/%Y"),
            "Serviço": servico,
            "Valor": f"R$ {valor}".replace(".", ","),
            "Conta": conta,
            "Cliente": cliente,
            "Combo": "",
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": chegada.strftime("%H:%M:%S"),
            "Hora Início": inicio.strftime("%H:%M:%S"),
            "Hora Saída": saida.strftime("%H:%M:%S"),
            "Hora Saída do Salão": saida_salao.strftime("%H:%M:%S")
        }
        registros.append(novo_registro)

    salvar_novos_dados(pd.DataFrame(registros))
    st.success(f"Atendimento registrado com sucesso para {cliente}! ({len(registros)} linha(s))")
    st.rerun()
