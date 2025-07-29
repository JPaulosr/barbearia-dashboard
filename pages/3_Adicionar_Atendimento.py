import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
import re

# === CONFIG ===
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

def validar_hora(h):
    return re.match(r"^\d{2}:\d{2}:\d{2}$", h)

# === TABELA DE PREÇOS PADRÃO ===
PRECOS_PADRAO = {
    "corte": 25.0,
    "pezinho": 7.0,
    "barba": 15.0,
    "sobrancelha": 7.0,  # corrigido para 7
    "luzes": 80.0,
    "pintura": 35.0,
    "alisamento": 40.0,
}

st.markdown("## 📝 Adicionar Atendimento Manual")

# === CARREGAMENTO INICIAL ===
df, aba = carregar_base()
clientes_existentes = sorted(df["Cliente"].dropna().unique())
formas_pagamento = sorted(df["Conta"].dropna().unique())
combos_existentes = sorted(df["Combo"].dropna().unique())

# === SERVIÇO SIMPLES ===
st.markdown("### ✂️ Selecione o Serviço e o Valor")
col3, col4 = st.columns([1, 1])
with col3:
    servico_simples = st.selectbox("Serviço (ex: corte)", options=[""] + sorted(PRECOS_PADRAO.keys()))
with col4:
    valor_padrao = PRECOS_PADRAO.get(servico_simples.lower(), 0.0) if servico_simples else ""
    valor_digitado = st.text_input("Valor do Serviço", value=str(valor_padrao) if valor_padrao else "")

# === FORMULÁRIO PRINCIPAL ===
with st.form("form_atendimento"):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        conta = st.selectbox("Forma de Pagamento", options=formas_pagamento)
        cliente_input = st.selectbox("Nome do Cliente", options=clientes_existentes)
        novo_cliente = st.text_input("Ou digite um novo nome de cliente")
        combo_input = st.selectbox("Combo (opcional - use 'corte+barba')", options=[""] + combos_existentes)
    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        h_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
        h_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
        h_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
        h_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

    submitted = st.form_submit_button("💾 Salvar Atendimento")

# === PROCESSAMENTO ===
if submitted:
    cliente = novo_cliente.strip() if novo_cliente else cliente_input.strip()
    conta = conta.strip()
    nova_data = data.strftime("%d/%m/%Y")
    fase = "Dono + funcionário"

    for label, hora in [("Hora Chegada", h_chegada), ("Hora Início", h_inicio), ("Hora Saída", h_saida), ("Hora Saída do Salão", h_saida_salao)]:
        if not validar_hora(hora):
            st.error(f"{label} inválida. Use HH:MM:SS.")
            st.stop()

    if combo_input:
        servicos_combo = combo_input.split("+")
        st.session_state.combo_pendente = {
            "data": nova_data,
            "conta": conta,
            "cliente": cliente,
            "combo": combo_input,
            "funcionario": funcionario,
            "fase": fase,
            "tipo": tipo,
            "horarios": {
                "chegada": h_chegada,
                "inicio": h_inicio,
                "saida": h_saida,
                "saida_salao": h_saida_salao
            },
            "servicos": servicos_combo
        }
        st.rerun()

    elif servico_simples:
        try:
            valor_final = float(valor_digitado.replace(",", "."))
        except:
            st.error("Valor do serviço inválido.")
            st.stop()

        nova_linha = {
            "Data": nova_data,
            "Serviço": servico_simples.lower(),
            "Valor": valor_final,
            "Conta": conta,
            "Cliente": cliente,
            "Combo": "",
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": h_chegada,
            "Hora Início": h_inicio,
            "Hora Saída": h_saida,
            "Hora Saída do Salão": h_saida_salao
        }

        df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
        set_with_dataframe(aba, df)
        st.success(f"✅ Atendimento salvo com sucesso para {cliente}!")
        st.rerun()
    else:
        st.warning("⚠️ Preencha o serviço ou o combo para continuar.")

# === FORMULÁRIO DE CONFIRMAÇÃO DE COMBO ===
if "combo_pendente" in st.session_state:
    combo_info = st.session_state.combo_pendente
    valores_combo = []
    erro_detectado = False

    st.markdown("### 💰 Edite os valores do combo antes de salvar:")
    with st.form("combo_form"):
        for serv in combo_info["servicos"]:
            serv_formatado = serv.strip().lower().replace(" ", "")
            if serv_formatado not in PRECOS_PADRAO:
                st.error(f"⚠️ Serviço '{serv}' não encontrado na tabela de preços.")
                erro_detectado = True
            else:
                valor_padrao = PRECOS_PADRAO[serv_formatado]
                valor_digitado = st.number_input(
                    f"{serv_formatado.capitalize()} (padrão: R$ {valor_padrao})",
                    value=valor_padrao,
                    key=f"combo_{serv_formatado}"
                )
                valores_combo.append((serv_formatado, valor_digitado))

        confirmar_combo = st.form_submit_button("✅ Confirmar e Salvar Combo")

    if confirmar_combo and not erro_detectado:
        for i, (serv, valor) in enumerate(valores_combo):
            nova_linha = {
                "Data": combo_info["data"],
                "Serviço": serv,
                "Valor": valor,
                "Conta": combo_info["conta"],
                "Cliente": combo_info["cliente"],
                "Combo": combo_info["combo"],
                "Funcionário": combo_info["funcionario"],
                "Fase": combo_info["fase"],
                "Tipo": combo_info["tipo"],
                "Hora Chegada": combo_info["horarios"]["chegada"] if i == 0 else "",
                "Hora Início": combo_info["horarios"]["inicio"] if i == 0 else "",
                "Hora Saída": combo_info["horarios"]["saida"] if i == 0 else "",
                "Hora Saída do Salão": combo_info["horarios"]["saida_salao"] if i == 0 else ""
            }
            df = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)

        set_with_dataframe(aba, df)
        st.success(f"✅ Combo registrado com sucesso para {combo_info['cliente']} ({len(valores_combo)} serviços)")
        del st.session_state.combo_pendente
        st.rerun()
