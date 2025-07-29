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

# === CONEXÃO COM GOOGLE SHEETS ===
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

df_base, aba_base = carregar_base()

st.markdown("### 📝 Adicionar Atendimento Manual")

# === CAMPOS DO FORMULÁRIO ===
with st.form("formulario_atendimento"):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        conta = st.selectbox("Forma de Pagamento", sorted(df_base["Conta"].dropna().unique()))
        cliente = st.selectbox(
            "Nome do Cliente", sorted(df_base["Cliente"].dropna().unique()), index=None, placeholder="Digite ou selecione"
        )
        combo = st.text_input("Combo (opcional - use 'corte+barba')", placeholder="corte+barba")

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        chegada = st.time_input("Hora de Chegada (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        inicio = st.time_input("Hora de Início (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        saida = st.time_input("Hora de Saída (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())
        saida_salao = st.time_input("Hora Saída do Salão (HH:MM:SS)", value=datetime.strptime("00:00:00", "%H:%M:%S").time())

    st.divider()

    linhas = []

    if combo:
        servicos_combo = [s.strip() for s in combo.lower().split("+")]
        for idx, servico in enumerate(servicos_combo):
            df_filtrado = df_base[df_base["Serviço"].str.lower() == servico]
            valores_numericos = (
                df_filtrado["Valor"]
                .dropna()
                .astype(str)
                .str.replace("R$", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.extract(r"(\d+\.\d+)")
                .dropna()
                .astype(float)
            )
            valor_padrao = valores_numericos.iloc[-1] if not valores_numericos.empty else 0

            valor_input = st.text_input(
                f"Valor do serviço: {servico}", 
                value=f"{valor_padrao:.2f}".replace(".", ","),
                key=f"valor_{servico}_{idx}"
            )

            linha = {
                "Data": data.strftime("%d/%m/%Y"),
                "Serviço": servico,
                "Valor": valor_input,
                "Conta": conta,
                "Cliente": cliente,
                "Combo": combo,
                "Funcionário": funcionario,
                "Fase": "Dono + funcionário",
                "Tipo": tipo,
                "Hora Chegada": chegada.strftime("%H:%M:%S") if idx == 0 else "",
                "Hora Início": inicio.strftime("%H:%M:%S") if idx == 0 else "",
                "Hora Saída": saida.strftime("%H:%M:%S") if idx == 0 else "",
                "Hora Saída do Salão": saida_salao.strftime("%H:%M:%S") if idx == 0 else "",
            }
            linhas.append(linha)
    else:
        servico = st.text_input("Serviço (ex: corte)")
        if servico:
            df_filtrado = df_base[df_base["Serviço"].str.lower() == servico.lower()]
            valores_numericos = (
                df_filtrado["Valor"]
                .dropna()
                .astype(str)
                .str.replace("R$", "", regex=False)
                .str.replace(",", ".", regex=False)
                .str.extract(r"(\d+\.\d+)")
                .dropna()
                .astype(float)
            )
            valor_padrao = valores_numericos.iloc[-1] if not valores_numericos.empty else 0

            valor_input = st.text_input("Valor do serviço", value=f"{valor_padrao:.2f}".replace(".", ","))

            linha = {
                "Data": data.strftime("%d/%m/%Y"),
                "Serviço": servico,
                "Valor": valor_input,
                "Conta": conta,
                "Cliente": cliente,
                "Combo": "",
                "Funcionário": funcionario,
                "Fase": "Dono + funcionário",
                "Tipo": tipo,
                "Hora Chegada": chegada.strftime("%H:%M:%S"),
                "Hora Início": inicio.strftime("%H:%M:%S"),
                "Hora Saída": saida.strftime("%H:%M:%S"),
                "Hora Saída do Salão": saida_salao.strftime("%H:%M:%S"),
            }
            linhas.append(linha)

    submitted = st.form_submit_button("💾 Salvar Atendimento")

    if submitted:
        if not cliente or not linhas:
            st.error("Preencha todos os campos obrigatórios.")
        else:
            df_existente = get_as_dataframe(aba_base).dropna(how="all")
            df_novo = pd.DataFrame(linhas)
            df_final = pd.concat([df_existente, df_novo], ignore_index=True)
            aba_base.clear()
            set_with_dataframe(aba_base, df_final)
            st.success(f"Atendimento registrado com sucesso para {cliente}! ({len(linhas)} linha(s))")
            st.rerun()
