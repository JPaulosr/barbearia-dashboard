# 11_Adicionar_Atendimento.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from datetime import datetime

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_CLIENTES = "clientes_status"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

# === CARREGAR DADOS ===
def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba

# === CONFIG PADRÃO ===
servicos_2025 = ["corte", "barba", "sobrancelha", "combo", "hidratação", "pomada"]
valores_fixos = {"corte": 25.0, "barba": 15.0, "sobrancelha": 10.0, "pomada": 15.0, "hidratação": 20.0}
funcionarios = ["JPaulo", "Vinicius"]
tipo_padrao = "Serviço"
formas_pagamento = ["Carteira", "Nubank", "Pix", "Dinheiro", "Pix Cliente", "Pagseguro"]

# === DADOS EXISTENTES ===
df_dados, aba_dados = carregar_base()
lista_clientes = sorted(df_dados["Cliente"].dropna().unique())
lista_combos = sorted(df_dados["Combo"].dropna().unique())

# === FORMULÁRIO ===
st.markdown("<h2 style='color:#f1c40f;'>🖋️ Adicionar Atendimento Manual</h2>", unsafe_allow_html=True)
st.markdown("""
<style>
    .stSelectbox, .stTextInput, .stDateInput, .stNumberInput, .stTextArea {
        background-color: #1c1c1c;
    }
</style>
""", unsafe_allow_html=True)

with st.form("formulario"):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today(), format="DD/MM/YYYY")
        conta = st.selectbox("Forma de Pagamento", options=formas_pagamento)

        cliente_selecionado = st.selectbox(
            "Nome do Cliente",
            options=[""] + lista_clientes,
            index=0,
            help="Digite o nome e veja se já existe. Se não existir, será cadastrado como novo."
        )
        if cliente_selecionado == "":
            cliente_input = st.text_input("Novo Cliente (não encontrado na lista)", key="cliente_manual").strip()
        else:
            cliente_input = cliente_selecionado

        combo_input_raw = st.selectbox(
            "Combo (opcional - use 'corte+barba')",
            options=[""] + lista_combos,
            index=0
        )
        combo_input = combo_input_raw.strip()

        if combo_input == "":
            servico = st.selectbox("Serviço", options=servicos_2025)
            valor = st.number_input("Valor", min_value=0.0, value=valores_fixos.get(servico, 0.0), step=0.5)

    with col2:
        funcionario = st.selectbox("Funcionário", options=funcionarios, index=0)
        tipo = tipo_padrao
        hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
        hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
        hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
        hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

    st.markdown("---")
    salvar = st.form_submit_button("📄 Salvar Atendimento")

# === AÇÃO ===
if salvar and cliente_input != "":
    nova_linha = []
    data_str = data.strftime("%d/%m/%Y")

    if combo_input:
        servicos_combo = [s.strip().lower() for s in combo_input.split("+")]
        for idx, serv in enumerate(servicos_combo):
            valor_combo = valores_fixos.get(serv, 0.0)
            if idx == 0:
                valor_editado = st.number_input(f"Valor do serviço: {serv}", min_value=0.0, value=valor_combo, step=0.5, key=f"valor_{serv}")
            else:
                valor_editado = valor_combo

            linha = {
                "Data": data_str,
                "Serviço": serv,
                "Valor": f"R$ {valor_editado:.2f}".replace(".", ","),
                "Conta": conta,
                "Cliente": cliente_input,
                "Combo": combo_input,
                "Funcionário": funcionario,
                "Fase": "Dono + funcionário",
                "Tipo": tipo,
                "Hora Chegada": hora_chegada if idx == 0 else "00:00:00",
                "Hora Início": hora_inicio if idx == 0 else "00:00:00",
                "Hora Saída": hora_saida if idx == 0 else "00:00:00",
                "Hora Saída do Salão": hora_saida_salao if idx == 0 else "00:00:00"
            }
            nova_linha.append(linha)
    else:
        linha = {
            "Data": data_str,
            "Serviço": servico,
            "Valor": f"R$ {valor:.2f}".replace(".", ","),
            "Conta": conta,
            "Cliente": cliente_input,
            "Combo": "",
            "Funcionário": funcionario,
            "Fase": "Dono + funcionário",
            "Tipo": tipo,
            "Hora Chegada": hora_chegada,
            "Hora Início": hora_inicio,
            "Hora Saída": hora_saida,
            "Hora Saída do Salão": hora_saida_salao
        }
        nova_linha.append(linha)

    df_atual = get_as_dataframe(aba_dados).dropna(how="all")
    df_novo = pd.concat([df_atual, pd.DataFrame(nova_linha)], ignore_index=True)
    set_with_dataframe(aba_dados, df_novo)
    st.success(f"Atendimento registrado com sucesso para {cliente_input}! ({len(nova_linha)} linha(s))")
    st.rerun()

