import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime

# === CONFIGURAÇÕES GLOBAIS ===
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

# === TABELA DE PREÇOS PADRÃO ===
PRECOS_PADRAO = {
    "corte": 25.0,
    "pezinho": 7.0,
    "barba": 15.0,
    "sobrancelha": 15.0,
    "luzes": 80.0,
    "pintura": 35.0,
}

# === TÍTULO ===
st.markdown("## 📝 Adicionar Atendimento Manual")

# === CARREGAR DADOS PARA AUTOCOMPLETE ===
df, aba = carregar_base()
clientes_existentes = sorted(df["Cliente"].dropna().unique())
formas_pagamento = sorted(df["Conta"].dropna().unique())
combos_existentes = sorted(df["Combo"].dropna().unique())

# === FORMULÁRIO ===
with st.form("form_atendimento"):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        conta = st.selectbox("Forma de Pagamento", options=formas_pagamento, placeholder="Selecione")
        cliente_input = st.selectbox("Nome do Cliente", options=clientes_existentes, placeholder="Digite ou selecione")
        novo_cliente = st.text_input("Ou digite um novo nome de cliente")
        combo_input = st.selectbox("Combo (opcional - use 'corte+barba')", options=[""] + combos_existentes, placeholder="Digite ou selecione")
    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        h_chegada = st.time_input("Hora de Chegada (HH:MM:SS)")
        h_inicio = st.time_input("Hora de Início (HH:MM:SS)")
        h_saida = st.time_input("Hora de Saída (HH:MM:SS)")
        h_saida_salao = st.time_input("Hora Saída do Salão (HH:MM:SS)")

    col3, col4 = st.columns([1, 1])
    with col3:
        servico_simples = st.selectbox("Serviço (ex: corte)", options=[""] + sorted(PRECOS_PADRAO.keys()))
    with col4:
        if servico_simples:
            valor_padrao = PRECOS_PADRAO.get(servico_simples.lower().strip(), 0.0)
            valor_digitado = st.text_input("Valor do Serviço", value=str(valor_padrao))
        else:
            valor_digitado = ""

    submitted = st.form_submit_button("💾 Salvar Atendimento")

# === PROCESSAMENTO ===
if submitted:
    nova_data = data.strftime("%d/%m/%Y")
    cliente = novo_cliente.strip() if novo_cliente else cliente_input.strip()
    conta = conta.strip()
    fase = "Dono + funcionário"

    # === TRATAMENTO DE COMBO ===
    if combo_input:
        servicos_combo = combo_input.split("+")
        valores_editados = []

        st.markdown("### 💰 Edite os valores antes de salvar:")
        with st.form("valores_combo"):
            for i, serv in enumerate(servicos_combo):
                serv = serv.strip().lower()
                valor_padrao = PRECOS_PADRAO.get(serv, 0.0)
                valor_digitado = st.number_input(f"{serv.capitalize()} (padrão: R$ {valor_padrao})", value=valor_padrao, key=f"val_{i}")
                valores_editados.append((serv, valor_digitado))
            confirmar = st.form_submit_button("✅ Confirmar e Salvar")

        if confirmar:
            for i, (serv, valor) in enumerate(valores_editados):
                nova_linha = {
                    "Data": nova_data,
                    "Serviço": serv,
                    "Valor": valor,
                    "Conta": conta,
                    "Cliente": cliente,
                    "Combo": combo_input,
                    "Funcionário": funcionario,
                    "Fase": fase,
                    "Tipo": tipo,
                    "Hora Chegada": h_chegada.strftime("%H:%M:%S") if i == 0 else "",
                    "Hora Início": h_inicio.strftime("%H:%M:%S") if i == 0 else "",
                    "Hora Saída": h_saida.strftime("%H:%M:%S") if i == 0 else "",
                    "Hora Saída do Salão": h_saida_salao.strftime("%H:%M:%S") if i == 0 else ""
                }
                df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

            set_with_dataframe(aba, df)
            st.success(f"Combo registrado com sucesso para {cliente}! ({len(valores_editados)} linha(s))")
            st.rerun()

    # === TRATAMENTO DE SERVIÇO SIMPLES ===
    elif servico_simples:
        servico = servico_simples.lower().strip()

        if valor_digitado:
            try:
                valor_final = float(valor_digitado.replace(",", "."))
            except:
                st.error("Erro: valor inválido.")
                st.stop()
        else:
            st.warning("Digite o valor do serviço.")
            st.stop()

        nova_linha = {
            "Data": nova_data,
            "Serviço": servico,
            "Valor": valor_final,
            "Conta": conta,
            "Cliente": cliente,
            "Combo": "",
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": h_chegada.strftime("%H:%M:%S"),
            "Hora Início": h_inicio.strftime("%H:%M:%S"),
            "Hora Saída": h_saida.strftime("%H:%M:%S"),
            "Hora Saída do Salão": h_saida_salao.strftime("%H:%M:%S")
        }

        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
        set_with_dataframe(aba, df)
        st.success(f"Atendimento registrado com sucesso para {cliente}.")
        st.rerun()

    else:
        st.warning("Preencha o serviço ou o combo para salvar.")
