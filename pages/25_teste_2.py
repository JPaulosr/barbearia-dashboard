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

# === FUNÇÕES AUXILIARES ===
def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Combo"] = df["Combo"].fillna("")  # Normaliza campo para evitar erro de comparação
    return df, aba

def salvar_base(df_final):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

def formatar_hora(valor):
    if re.match(r"^\d{2}:\d{2}:\d{2}$", valor):
        return valor
    return "00:00:00"

def obter_valor_servico(servico):
    return valores_servicos.get(servico.lower(), 0.0)

def ja_existe_atendimento(cliente, data, servico, combo=""):
    df, _ = carregar_base()
    df["Combo"] = df["Combo"].fillna("")
    existe = df[
        (df["Cliente"] == cliente) &
        (df["Data"] == data) &
        (df["Serviço"] == servico) &
        (df["Combo"] == combo)
    ]
    return not existe.empty

# === VALORES PADRÃO DE SERVIÇO ===
valores_servicos = {
    "corte": 25.0,
    "pezinho": 7.0,
    "barba": 15.0,
    "sobrancelha": 7.0,
    "luzes": 80.0,
    "pintura": 35.0,
    "alisamento": 40.0,
}

# === INTERFACE ===
st.title("📅 Adicionar Atendimento")
df_existente, _ = carregar_base()

# Converte a coluna "Data" para datetime
df_existente["Data"] = pd.to_datetime(df_existente["Data"], format="%d/%m/%Y", errors="coerce")

# Filtra apenas os registros de 2025
df_2025 = df_existente[df_existente["Data"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025["Serviço"] = (
    df_2025["Serviço"]
    .dropna()
    .str.strip()
    .str.lower()
    .str.capitalize()
)

servicos_existentes = sorted(df_2025["Serviço"].unique())
contas_existentes = sorted(df_2025["Conta"].dropna().unique())
combos_existentes = sorted(df_2025["Combo"].dropna().unique())

col1, col2 = st.columns(2)
with col1:
    data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")
    conta = st.selectbox("Forma de Pagamento", contas_existentes + ["Carteira", "Nubank"])
    cliente = st.selectbox("Nome do Cliente", clientes_existentes)
    novo_nome = st.text_input("Ou digite um novo nome de cliente")
    cliente = novo_nome if novo_nome else cliente
    combo = st.selectbox("Combo (opcional - use 'corte+barba')", [""] + combos_existentes)

with col2:
    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
    hora_chegada = st.text_input("Hora de Chegada (HH:MM:SS)", "00:00:00")
    hora_inicio = st.text_input("Hora de Início (HH:MM:SS)", "00:00:00")
    hora_saida = st.text_input("Hora de Saída (HH:MM:SS)", "00:00:00")
    hora_salao = st.text_input("Hora Saída do Salão (HH:MM:SS)", "00:00:00")

fase = "Dono + funcionário"

# === CONTROLE DE ESTADO ===
if "combo_salvo" not in st.session_state:
    st.session_state.combo_salvo = False
if "simples_salvo" not in st.session_state:
    st.session_state.simples_salvo = False

# === FUNÇÕES DE SALVAMENTO ===
def salvar_combo(combo, valores_customizados):
    df, _ = carregar_base()
    servicos = combo.split("+")
    novas_linhas = []
    for i, servico in enumerate(servicos):
        valor = valores_customizados.get(servico, obter_valor_servico(servico))
        linha = {
            "Data": data,
            "Serviço": servico,
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
            "Hora Saída do Salão": hora_salao if i == 0 else "",
        }
        novas_linhas.append(linha)
    df_final = pd.concat([df, pd.DataFrame(novas_linhas)], ignore_index=True)
    salvar_base(df_final)

def salvar_simples(servico, valor):
    df, _ = carregar_base()
    nova_linha = {
        "Data": data,
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
        "Hora Saída do Salão": hora_salao,
    }
    df_final = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    salvar_base(df_final)

# === FORMULÁRIO ===
if combo:
    st.subheader("💰 Edite os valores do combo antes de salvar:")
    valores_customizados = {}
    for servico in combo.split("+"):
        valor_padrao = obter_valor_servico(servico)
        valor = st.number_input(f"{servico.capitalize()} (padrão: R$ {valor_padrao})", value=valor_padrao, step=1.0, key=f"valor_{servico}")
        valores_customizados[servico] = valor

    if not st.session_state.combo_salvo:
        if st.button("✅ Confirmar e Salvar Combo"):
            duplicado = False
            for s in combo.split("+"):
                if ja_existe_atendimento(cliente, data, s, combo):
                    duplicado = True
                    break
            if duplicado:
                st.warning("⚠️ Combo já registrado para este cliente e data.")
            else:
                salvar_combo(combo, valores_customizados)
                st.session_state.combo_salvo = True
    else:
        if st.button("➕ Novo Atendimento"):
           st.session_state.combo_salvo = False
           st.rerun()

else:
    st.subheader("✂️ Selecione o serviço e valor:")
    servico = st.selectbox("Serviço", servicos_existentes + list(valores_servicos.keys()))
    valor_sugerido = obter_valor_servico(servico)
    valor = st.number_input("Valor", value=valor_sugerido, step=1.0)

    if not st.session_state.simples_salvo:
        if st.button("📁 Salvar Atendimento"):
            if ja_existe_atendimento(cliente, data, servico):
                st.warning("⚠️ Atendimento já registrado para este cliente, data e serviço.")
            else:
                salvar_simples(servico, valor)
                st.session_state.simples_salvo = True
    else:
        if st.button("➕ Novo Atendimento"):
           st.session_state.simples_salvo = False
           st.rerun()

