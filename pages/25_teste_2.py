import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
import re
import unicodedata

# === FUNÇÃO DE NORMALIZAÇÃO ===
def normalizar(texto):
    return unicodedata.normalize("NFKD", texto.strip().lower()).encode("ASCII", "ignore").decode()

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
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df, aba

def carregar_clientes():
    aba = conectar_sheets().worksheet(ABA_CLIENTES)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df

def salvar_novo_atendimento(novo_df):
    df_existente, aba = carregar_base()
    df_final = pd.concat([df_existente, novo_df], ignore_index=True)
    set_with_dataframe(aba, df_final)

def salvar_novo_cliente(nome):
    aba = conectar_sheets().worksheet(ABA_CLIENTES)
    df_atual = get_as_dataframe(aba).dropna(how="all")
    novo = pd.DataFrame([{
        "Cliente": nome,
        "Status": "Ativo",
        "Foto": "",
        "Família": ""
    }])
    df_final = pd.concat([df_atual, novo], ignore_index=True)
    set_with_dataframe(aba, df_final)

def validar_hora(hora):
    return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}", hora))

# === DADOS BASE ===
df_clientes = carregar_clientes()
df_base, _ = carregar_base()

df_base["Data"] = pd.to_datetime(df_base["Data"], dayfirst=True, errors='coerce')
servicos_2025 = sorted(df_base[df_base["Data"].dt.year == 2025]["Serviço"].dropna().unique())

valores_referencia = (
    df_base[df_base["Valor"].notna() & df_base["Valor"].astype(str).str.startswith("R$")]
    .assign(valor_num=lambda d: d["Valor"].astype(str).str.replace("R\$", "", regex=True).str.replace(",", ".").astype(float))
    .groupby("Serviço")["valor_num"]
    .mean()
    .round(2)
    .to_dict()
)

valores_fixos = {
    "corte": 25.00,
    "barba": 15.00,
    "alisamento": 40.00,
    "pezinho": 7.00,
    "luzes": 45.00,
    "sobrancelha": 7.00,
    "gel": 10.00,
    "pomada": 15.00,
    "tintura": 20.00
}

formas_pagamento = df_base["Conta"].dropna().astype(str).unique().tolist()
lista_clientes = df_clientes["Cliente"].dropna().astype(str).unique().tolist()
lista_combos = df_base["Combo"].dropna().astype(str).unique().tolist()

# === CONTROLE DE ESTADO ===
if "servico_selecionado" not in st.session_state:
    st.session_state.servico_selecionado = None

if "valor_personalizado" not in st.session_state:
    st.session_state.valor_personalizado = None

# === FORMULÁRIO ===
st.title("✍️ Adicionar Atendimento Manual")

with st.form("formulario_atendimento", clear_on_submit=False):
    col1, col2 = st.columns(2)

    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today(), format="DD/MM/YYYY")
        servico = st.selectbox("Serviço", options=servicos_2025)

        # Atualizar valor fixo se serviço mudou
        servico_key = normalizar(servico)
        valor_fixo = valores_fixos.get(servico_key, valores_referencia.get(servico, 0.0))

        if st.session_state.servico_selecionado != servico:
            st.session_state.valor_personalizado = valor_fixo
            st.session_state.servico_selecionado = servico

        valor = st.number_input(
            "Valor (R$)",
            min_value=0.0,
            step=0.5,
            format="%.2f",
            value=st.session_state.valor_personalizado
        )

        conta = st.selectbox("Forma de Pagamento", options=formas_pagamento)

        cliente_input = st.text_input("Nome do Cliente").strip()
        sugestoes = [c for c in lista_clientes if cliente_input.lower() in c.lower()] if cliente_input else []
        if sugestoes:
            st.markdown("🔍 **Clientes semelhantes encontrados:**")
            for s in sugestoes[:5]:
                st.markdown(f"- {s}")

        combo_input = st.text_input("Combo (opcional)").strip()
        sugestoes_combo = [c for c in lista_combos if combo_input.lower() in c.lower()] if combo_input else []
        if sugestoes_combo:
            st.markdown("🔍 **Combos semelhantes encontrados:**")
            for s in sugestoes_combo[:5]:
                st.markdown(f"- {s}")

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        fase = st.selectbox("Fase", ["Autônomo (prestador)", "Dono (sozinho)", "Dono + funcionário"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
        hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
        hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
        hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

    enviar = st.form_submit_button("💾 Salvar Atendimento")

# === SALVAR ===
if enviar:
    campos_hora = [hora_chegada, hora_inicio, hora_saida, hora_saida_salao]
    if not all(validar_hora(h) for h in campos_hora):
        st.error("❗ Todos os campos de hora devem estar no formato HH:MM:SS.")
    elif cliente_input == "" or servico == "":
        st.error("❗ Nome do cliente e serviço são obrigatórios.")
    else:
        cliente = cliente_input
        familia = ""
        cliente_encontrado = df_clientes[df_clientes["Cliente"].str.lower() == cliente.lower()]
        if not cliente_encontrado.empty and "Família" in cliente_encontrado.columns:
            familia = cliente_encontrado.iloc[0]["Família"]

        if cliente not in lista_clientes:
            salvar_novo_cliente(cliente)

        novo = pd.DataFrame([{
            "Data": data.strftime("%d/%m/%Y"),
            "Serviço": servico,
            "Valor": f"R$ {valor:.2f}",
            "Conta": conta,
            "Cliente": cliente,
            "Combo": combo_input,
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Hora Chegada": hora_chegada,
            "Hora Início": hora_inicio,
            "Hora Saída": hora_saida,
            "Hora Saída do Salão": hora_saida_salao,
            "Família": familia
        }])

        salvar_novo_atendimento(novo)
        st.success("✅ Atendimento salvo com sucesso!")
        st.session_state["salvo"] = True
        st.query_params.update(recarga="ok")
        st.rerun()

# === RECARREGAMENTO ===
if st.session_state.get("salvo"):
    st.success("✅ Atendimento registrado.")
    st.session_state["salvo"] = False
