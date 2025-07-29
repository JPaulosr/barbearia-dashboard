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

# === CARREGAR DADOS BASE ===
df_clientes = carregar_clientes()
df_base, _ = carregar_base()

# Serviços 2025
df_base["Data"] = pd.to_datetime(df_base["Data"], dayfirst=True, errors='coerce')
servicos_2025 = df_base[df_base["Data"].dt.year == 2025]["Serviço"].dropna().unique().tolist()
servicos_2025 = sorted(set(servicos_2025))

# Valores médios por serviço
valores_referencia = (
    df_base[df_base["Valor"].notna() & df_base["Valor"].astype(str).str.startswith("R$")]
    .assign(
        valor_num=lambda d: pd.to_numeric(
            d["Valor"].astype(str)
            .str.replace("R\\$", "", regex=True)
            .str.replace(",", "."),
            errors="coerce"
        )
    )
    .groupby("Serviço")["valor_num"]
    .mean()
    .round(2)
    .to_dict()
)

# Contas (formas de pagamento)
formas_pagamento = df_base["Conta"].dropna().astype(str).unique().tolist()

# Clientes e combos
lista_clientes = df_clientes["Cliente"].dropna().astype(str).unique().tolist()
lista_combos = df_base["Combo"].dropna().astype(str).unique().tolist()

# === FORMULÁRIO ===
st.title("✍️ Adicionar Atendimento Manual")

with st.form("formulario_atendimento", clear_on_submit=False):
    col1, col2 = st.columns(2)

    with col1:
        data = st.date_input("Data do Atendimento", value=datetime.today(), format="DD/MM/YYYY")
        servico = st.selectbox("Serviço", options=servicos_2025)
        valor_padrao = valores_referencia.get(servico, 0.0)
        valor = st.number_input("Valor (R$)", value=valor_padrao, min_value=0.0, step=0.5, format="%.2f")
        conta = st.selectbox("Forma de Pagamento", options=formas_pagamento)

        cliente = st.text_input("Nome do Cliente", placeholder="Digite o nome do cliente")

        if cliente and len(cliente) >= 2:
            sugestoes_cliente = [c for c in lista_clientes if cliente.lower() in c.lower()]
            if sugestoes_cliente:
                with st.expander("🔍 Clientes semelhantes encontrados"):
                    for s in sugestoes_cliente[:10]:
                        st.markdown(f"- `{s}`")

        if cliente:
            try:
                linha_cliente = df_clientes[df_clientes["Cliente"].str.lower() == cliente.lower()]
                if not linha_cliente.empty and "Foto" in linha_cliente.columns:
                    foto_url = linha_cliente.iloc[0]["Foto"]
                    if isinstance(foto_url, str) and foto_url.strip() != "":
                        st.image(foto_url, width=150, caption=f"📸 Foto de {cliente}")
                    else:
                        st.info("Cliente sem foto cadastrada.")
            except Exception as e:
                st.warning(f"Erro ao carregar a foto: {e}")

        combo_input = st.selectbox(
            "Combo (opcional)",
            options=[""] + sorted(lista_combos),
            index=0,
            placeholder="Digite ou selecione um combo",
        )

        sugestoes = []
        if combo_input and len(combo_input) >= 2:
            sugestoes = [c for c in lista_combos if combo_input.lower() in c.lower()]
        if sugestoes:
            with st.expander("🔍 Sugestões de combos"):
                for s in sugestoes:
                    st.markdown(f"- `{s}`")

    with col2:
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
        fase = st.selectbox("Fase", ["Autônomo (prestador)", "Dono (sozinho)", "Dono + funcionário"])
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
        hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", value="00:00:00")
        hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", value="00:00:00")
        hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", value="00:00:00")
        hora_saida_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", value="00:00:00")

    enviar = st.form_submit_button("📂 Salvar Atendimento")

# === AÇÃO AO ENVIAR ===
if enviar:
    campos_hora = [hora_chegada, hora_inicio, hora_saida, hora_saida_salao]
    if not all(validar_hora(h) for h in campos_hora):
        st.error("❗ Todos os campos de hora devem estar no formato HH:MM:SS.")
    elif cliente.strip() == "" or servico.strip() == "":
        st.error("❗ Nome do cliente e serviço são obrigatórios.")
    else:
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
        st.experimental_rerun()

# === RECARREGAMENTO SEGURO APÓS SALVAR ===
if st.session_state.get("salvo"):
    st.success("✅ Atendimento registrado.")
    st.session_state["salvo"] = False
