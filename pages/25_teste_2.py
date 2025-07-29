import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
import re
import unicodedata

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

def salvar_novo_atendimento(novos_df):
    df_existente, aba = carregar_base()
    df_final = pd.concat([df_existente, novos_df], ignore_index=True)
    set_with_dataframe(aba, df_final)

def salvar_novo_cliente(nome):
    aba = conectar_sheets().worksheet(ABA_CLIENTES)
    df_atual = get_as_dataframe(aba).dropna(how="all")
    novo = pd.DataFrame([{ "Cliente": nome, "Status": "Ativo", "Foto": "", "Família": "" }])
    df_final = pd.concat([df_atual, novo], ignore_index=True)
    set_with_dataframe(aba, df_final)

def validar_hora(hora):
    return bool(re.fullmatch(r"\d{2}:\d{2}:\d{2}", hora))

def normalizar(texto):
    return unicodedata.normalize("NFKD", texto.strip().lower()).encode("ASCII", "ignore").decode()

# === DADOS BASE ===
df_clientes = carregar_clientes()
df_base, _ = carregar_base()
df_base["Data"] = pd.to_datetime(df_base["Data"], dayfirst=True, errors='coerce')
servicos_2025 = sorted(df_base[df_base["Data"].dt.year == 2025]["Serviço"].dropna().unique())

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

# === FORMULÁRIO ===
with st.form("formulario_atendimento", clear_on_submit=False):
    st.title("✍️ Adicionar Atendimento Manual")

    data = st.date_input("Data do Atendimento", value=datetime.today(), format="DD/MM/YYYY")
    conta = st.selectbox("Forma de Pagamento", options=formas_pagamento)
    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
    fase = st.selectbox("Fase", ["Autônomo (prestador)", "Dono (sozinho)", "Dono + funcionário"])
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
    hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
    hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
    hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
    hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

    cliente_nome = st.selectbox("Nome do Cliente", options=[""] + lista_clientes, key="cliente")
    if cliente_nome == "":
        cliente_nome = st.text_input("Novo Cliente", key="cliente_manual").strip()

    combo_selecionado = st.selectbox(
    "Combo (ex: corte+barba)",
    options=[""] + lista_combos,
    index=0,
    help="Digite ou selecione um combo já usado anteriormente",
    placeholder="Digite ou selecione o combo",
    key="combo"
)

if combo_selecionado == "":
    combo_bruto = st.text_input("Novo Combo", key="combo_manual").strip().lower()
else:
    combo_bruto = combo_selecionado.strip().lower()

    enviar = st.form_submit_button("💾 Salvar Atendimento")

if enviar:
    campos_hora = [hora_chegada, hora_inicio, hora_saida, hora_saida_salao]
    if not all(validar_hora(h) for h in campos_hora):
        st.error("❗ Todos os campos de hora devem estar no formato HH:MM:SS.")
    elif cliente_nome == "":
        st.error("❗ Nome do cliente é obrigatório.")
    elif combo_bruto == "":
        st.error("❗ Combo não pode estar vazio.")
    else:
        servicos_combo = [s.strip() for s in combo_bruto.split("+")]
        dados_linhas = []

        for i, serv in enumerate(servicos_combo):
            serv_key = normalizar(serv)
            valor_padrao = valores_fixos.get(serv_key, 0.0)
            valor_input = st.number_input(f"Valor para '{serv}'", min_value=0.0, step=0.5, format="%.2f", value=valor_padrao, key=f"valor_{i}")

            dados_linhas.append({
                "Serviço": serv,
                "Valor": f"R$ {valor_input:.2f}"
            })

        confirmar = st.button("✅ Confirmar e Salvar Combo")
        if confirmar:
            familia = ""
            cliente_encontrado = df_clientes[df_clientes["Cliente"].str.lower() == cliente_nome.lower()]
            if not cliente_encontrado.empty and "Família" in cliente_encontrado.columns:
                familia = cliente_encontrado.iloc[0]["Família"]

            if cliente_nome not in lista_clientes:
                salvar_novo_cliente(cliente_nome)

            df_final = pd.DataFrame([{
                "Data": data.strftime("%d/%m/%Y"),
                "Serviço": linha["Serviço"],
                "Valor": linha["Valor"],
                "Conta": conta,
                "Cliente": cliente_nome,
                "Combo": combo_bruto,
                "Funcionário": funcionario,
                "Fase": fase,
                "Tipo": tipo,
                "Hora Chegada": hora_chegada,
                "Hora Início": hora_inicio,
                "Hora Saída": hora_saida,
                "Hora Saída do Salão": hora_saida_salao,
                "Família": familia
            } for linha in dados_linhas])

            salvar_novo_atendimento(df_final)
            st.success("✅ Combo registrado com sucesso!")
            st.rerun()
