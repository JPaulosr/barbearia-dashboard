import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
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

def carregar_base():
    planilha = conectar_sheets()
    aba_dados = planilha.worksheet(ABA_DADOS)
    df = get_as_dataframe(aba_dados).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba_dados

def carregar_clientes():
    planilha = conectar_sheets()
    aba = planilha.worksheet(ABA_CLIENTES)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df

def salvar_novo_atendimento(novo_df):
    df_existente, aba = carregar_base()
    df_atualizado = pd.concat([df_existente, novo_df], ignore_index=True)
    set_with_dataframe(aba, df_atualizado)

# === INTERFACE ===
st.title("✍️ Adicionar Atendimento Manual")

df_clientes = carregar_clientes()
df_base, _ = carregar_base()

lista_clientes = df_clientes["Cliente"].dropna().astype(str).unique().tolist()
lista_servicos = df_base["Serviço"].dropna().astype(str).unique().tolist()

with st.form("formulario_atendimento", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today())
        servico = st.selectbox("Serviço", options=sorted(lista_servicos))
        valor = st.number_input("Valor (R$)", min_value=0.0, step=0.5, format="%.2f")
        conta = st.selectbox("Conta", ["Carteira", "Nubank"])
        cliente = st.text_input("Nome do Cliente").strip()
        combo = st.text_input("Combo (deixe vazio se não for combo)").strip()

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        fase = st.selectbox("Fase", ["Autônomo (prestador)", "Dono (sozinho)", "Dono + funcionário"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        hora_chegada = st.time_input("Hora de Chegada")
        hora_inicio = st.time_input("Hora de Início")
        hora_saida = st.time_input("Hora de Saída")
        hora_saida_salao = st.time_input("Hora Saída do Salão")

    enviar = st.form_submit_button("💾 Salvar Atendimento")

# === EXIBIR FOTO DO CLIENTE ===
if cliente:
    cliente_filtrado = df_clientes[df_clientes["Cliente"].str.lower() == cliente.lower()]
    if not cliente_filtrado.empty and "Foto" in cliente_filtrado.columns:
        link_foto = cliente_filtrado.iloc[0]["Foto"]
        if isinstance(link_foto, str) and link_foto.startswith("http"):
            st.image(link_foto, width=150, caption="Foto do cliente")

# === AÇÃO DE ENVIO ===
if enviar:
    if cliente == "" or servico == "":
        st.error("❗ Nome do cliente e serviço são obrigatórios.")
    else:
        # Buscar família se existir
        familia = ""
        cliente_match = df_clientes[df_clientes["Cliente"].str.lower() == cliente.lower()]
        if not cliente_match.empty and "Família" in cliente_match.columns:
            familia = cliente_match.iloc[0]["Família"]

        novo = pd.DataFrame([{
            "Data": data.strftime("%d/%m/%Y"),
            "Serviço": servico,
            "Valor": f"R$ {valor:.2f}",
            "Conta": conta,
            "Cliente": cliente,
            "Combo": combo,
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": hora_chegada.strftime("%H:%M:%S"),
            "Hora Início": hora_inicio.strftime("%H:%M:%S"),
            "Hora Saída": hora_saida.strftime("%H:%M:%S"),
            "Hora Saída do Salão": hora_saida_salao.strftime("%H:%M:%S"),
            "Família": familia  # salvando família como campo extra
        }])

        salvar_novo_atendimento(novo)
        st.success("✅ Atendimento salvo com sucesso!")

        # Limpar formulário (recursivamente recarrega a página)
        st.experimental_rerun()
