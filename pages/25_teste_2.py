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

# === FUNÇÕES AUXILIARES ===
def carregar_dados_existentes():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba

def salvar_novos_registros(linhas):
    df_existente, aba = carregar_dados_existentes()
    df_novo = pd.DataFrame(linhas)
    df_final = pd.concat([df_existente, df_novo], ignore_index=True)
    set_with_dataframe(aba, df_final)

# === BASE DE VALORES PADRÕES ===
valores_servicos = {
    "corte": 25.0,
    "pezinho": 7.0,
    "barba": 15.0,
    "sobrancelha": 7.0,
    "luzes": 80.0,
    "pintura": 35.0,
    "alisamento": 40.0,
}

# === FORMULÁRIO PRINCIPAL ===
st.title("📅 Adicionar Atendimento")

exibir_formulario = True
if "salvou" not in st.session_state:
    st.session_state.salvou = False

if st.session_state.salvou:
    st.success("✅ Atendimento salvo com sucesso!")
    if st.button("➕ Cadastrar novo atendimento"):
        st.session_state.salvou = False
        st.experimental_rerun()
    exibir_formulario = False

if exibir_formulario:
    col1, col2 = st.columns(2)

    with col1:
        data = st.date_input("Data", value=datetime.today()).strftime("%Y-%m-%d")
        conta = st.selectbox("Forma de Pagamento", ["Carteira", "Nubank"])
        cliente = st.text_input("Nome do Cliente")
        combo = st.selectbox("Combo (opcional - use 'corte+barba')", ["", "corte+barba", "corte+barba+sobrancelha"])

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)")
        hora_inicio = st.text_input("Hora de Início (HH:MM:SS)")
        hora_saida = st.text_input("Hora de Saída (HH:MM:SS)")
        hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)")

    fase = "Dono + funcionário"

    def salvar_atendimento_simples():
        novo = {
            "Data": data,
            "Serviço": st.selectbox("Serviço", list(valores_servicos.keys()), key="servico_simples"),
            "Valor": st.number_input("Valor", step=1.0, key="valor_simples"),
            "Conta": conta,
            "Cliente": cliente,
            "Combo": "",
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": hora_chegada,
            "Hora Início": hora_inicio,
            "Hora Saída": hora_saida,
            "Hora Saída do Salão": hora_saida_salao,
        }
        salvar_novos_registros([novo])
        st.session_state.salvou = True
        st.experimental_rerun()

    def salvar_combo():
        partes = combo.split("+")
        linhas = []
        for i, servico in enumerate(partes):
            linha = {
                "Data": data,
                "Serviço": servico,
                "Valor": valores_servicos.get(servico.lower(), 0.0),
                "Conta": conta,
                "Cliente": cliente,
                "Combo": combo,
                "Funcionário": funcionario,
                "Fase": fase,
                "Tipo": tipo,
                "Hora Chegada": hora_chegada if i == 0 else "",
                "Hora Início": hora_inicio if i == 0 else "",
                "Hora Saída": hora_saida if i == 0 else "",
                "Hora Saída do Salão": hora_saida_salao if i == 0 else "",
            }
            linhas.append(linha)
        salvar_novos_registros(linhas)
        st.session_state.salvou = True
        st.experimental_rerun()

    if combo:
        st.subheader("💰 Edite os valores do combo antes de salvar:")
        for servico in combo.split("+"):
            valor_padrao = valores_servicos.get(servico.lower(), 0.0)
            valor = st.number_input(f"{servico.capitalize()} (padrão: R$ {valor_padrao})", value=valor_padrao, step=1.0)
            valores_servicos[servico.lower()] = valor
        if st.button("✅ Confirmar e Salvar Combo"):
            salvar_combo()
    else:
        if st.button("📁 Salvar Atendimento"):
            salvar_atendimento_simples()
