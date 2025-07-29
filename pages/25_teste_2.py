import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
import re

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

df, aba = carregar_base()

st.title("📝 Adicionar Atendimento Manual")

# === Valores únicos dos campos ===
clientes = sorted(df["Cliente"].dropna().unique())
pagamentos = sorted(df["Conta"].dropna().unique())
servicos_cadastrados = sorted(df["Serviço"].dropna().unique())
combos_cadastrados = sorted(df["Combo"].dropna().unique())

# === Tabela fixa de preços (você pode editar conforme necessário) ===
precos_fixos = {
    "pezinho": 7.00,
    "corte": 25.00,
    "barba": 15.00,
    "sobrancelha": 10.00,
    "luzes": 150.00,
    "hidratação": 30.00,
    "selagem": 120.00,
    "progressiva": 150.00
}

# === CAMPOS DO FORMULÁRIO ===
col1, col2 = st.columns(2)
with col1:
    data = st.date_input("Data do Atendimento", value=datetime.today())
    conta = st.selectbox("Forma de Pagamento", pagamentos)
    cliente = st.selectbox("Nome do Cliente", options=clientes + ["Digite um novo nome..."])
    combo = st.selectbox("Combo (opcional - use 'corte+barba')", options=[""] + combos_cadastrados)
with col2:
    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
    hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
    hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
    hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
    hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

# === SERVIÇO INDIVIDUAL ===
servico = st.selectbox("Serviço (ex: corte)", options=[""] + servicos_cadastrados)

# === VALOR AUTOMÁTICO AO ESCOLHER SERVIÇO ===
valor_default = precos_fixos.get(servico.lower(), "")
valor_manual = st.text_input(f"Valor do serviço: {servico.lower() if servico else ''}", value=str(valor_default).replace('.', ','))

# === BOTÃO SALVAR ===
if st.button("💾 Salvar Atendimento"):
    data_str = data.strftime("%d/%m/%Y")
    fase = "Dono + funcionário"

    # === Função para validar horário ===
    def validar_hora(h):
        return bool(re.match(r"^\d{2}:\d{2}:\d{2}$", h.strip()))

    if not all([validar_hora(h) for h in [hora_chegada, hora_inicio, hora_saida, hora_saida_salao]]):
        st.error("⛔ Formato de hora inválido. Use HH:MM:SS.")
    else:
        linhas = []

        # === REGISTRO DE COMBO ===
        if combo:
            servicos_combo = combo.split("+")
            for i, srv in enumerate(servicos_combo):
                valor = ""
                if i == 0:
                    try:
                        valor = float(valor_manual.replace(",", "."))
                    except:
                        st.error("⛔ Valor inválido.")
                        st.stop()
                else:
                    valor = precos_fixos.get(srv.lower(), 0)

                linha = {
                    "Data": data_str,
                    "Serviço": srv,
                    "Valor": valor,
                    "Conta": conta,
                    "Cliente": cliente,
                    "Combo": combo,
                    "Funcionário": funcionario,
                    "Fase": fase,
                    "Tipo": tipo,
                    "Hora Chegada": hora_chegada if i == 0 else "",
                    "Hora Início": hora_inicio if i == 0 else "",
                    "Hora Saída": hora_saida if i == 0 else "",
                    "Hora Saída do Salão": hora_saida_salao if i == 0 else ""
                }
                linhas.append(linha)
        else:
            # Atendimento simples
            try:
                valor = float(valor_manual.replace(",", "."))
            except:
                st.error("⛔ Valor inválido.")
                st.stop()

            linha = {
                "Data": data_str,
                "Serviço": servico,
                "Valor": valor,
                "Conta": conta,
                "Cliente": cliente,
                "Combo": "",
                "Funcionário": funcionario,
                "Fase": fase,
                "Tipo": tipo,
                "Hora Chegada": hora_chegada,
                "Hora Início": hora_inicio,
                "Hora Saída": hora_saida,
                "Hora Saída do Salão": hora_saida_salao
            }
            linhas.append(linha)

        # === SALVAR NO GOOGLE SHEETS ===
        df_existente = get_as_dataframe(aba).dropna(how="all")
        df_novo = pd.concat([df_existente, pd.DataFrame(linhas)], ignore_index=True)
        aba.clear()
        set_with_dataframe(aba, df_novo)

        st.success(f"✅ Atendimento registrado com sucesso para {cliente}! ({len(linhas)} linha(s))")
        st.stop()
