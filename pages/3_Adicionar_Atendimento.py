import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

# Colunas “oficiais” e colunas de FIADO que devemos preservar
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]  # incluo DataPagamento p/ competência

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def ler_cabecalho(aba):
    """Retorna a primeira linha (cabeçalho) já existente na planilha, se houver."""
    try:
        headers = aba.row_values(1)
        headers = [h.strip() for h in headers] if headers else []
        return headers
    except Exception:
        return []

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]

    # >>> Garante colunas oficiais e de fiado (sem remover as que já existem)
    for coluna in [*COLS_OFICIAIS, *COLS_FIADO]:
        if coluna not in df.columns:
            df[coluna] = ""

    # Normaliza Período
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""

    df["Combo"] = df["Combo"].fillna("")

    return df, aba

def salvar_base(df_final):
    """
    Salva preservando TODAS as colunas existentes na planilha.
    1) Lê o cabeçalho atual;
    2) Garante oficiais + fiado;
    3) Reordena por cabeçalho atual (para não ‘sumir’ colunas);
    4) Preenche vazios onde necessário.
    """
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = ler_cabecalho(aba)

    # Se a planilha estiver vazia (sem cabeçalho), cria um com oficiais + fiado
    if not headers_existentes:
        headers_existentes = [*COLS_OFICIAIS, *COLS_FIADO]

    # Garante todas as colunas do cabeçalho + oficiais + fiado
    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_FIADO]))
    for col in colunas_alvo:
        if col not in df_final.columns:
            df_final[col] = ""

    # Reordena pelas colunas alvo (preserva as extras que já existiam)
    df_final = df_final[colunas_alvo]

    # Escreve
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

def obter_valor_servico(servico):
    for chave in valores_servicos.keys():
        if chave.lower() == servico.lower():
            return valores_servicos[chave]
    return 0.0

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
    "Corte": 25.0,
    "Pezinho": 7.0,
    "Barba": 15.0,
    "Sobrancelha": 7.0,
    "Luzes": 45.0,
    "Pintura": 35.0,
    "Alisamento": 40.0,
    "Gel": 10.0,
    "Pomada": 15.0,
}

# === INTERFACE ===
st.title("📅 Adicionar Atendimento")

df_existente, _ = carregar_base()
df_existente["Data"] = pd.to_datetime(df_existente["Data"], format="%d/%m/%Y", errors="coerce")
df_2025 = df_existente[df_existente["Data"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025 = df_2025[df_2025["Serviço"].notna()].copy()
servicos_existentes = sorted(df_2025["Serviço"].str.strip().unique())
contas_existentes = sorted(df_2025["Conta"].dropna().unique())
combos_existentes = sorted(df_2025["Combo"].dropna().unique())

# === SELEÇÃO E AUTOPREENCHIMENTO ===
col1, col2 = st.columns(2)

with col1:
    data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")
    cliente = st.selectbox("Nome do Cliente", clientes_existentes)
    novo_nome = st.text_input("Ou digite um novo nome de cliente")
    cliente = novo_nome if novo_nome else cliente

    ultimo = df_existente[df_existente["Cliente"] == cliente]
    ultimo = ultimo.sort_values("Data", ascending=False).iloc[0] if not ultimo.empty else None
    conta_sugerida = ultimo["Conta"] if ultimo is not None else ""
    funcionario_sugerido = ultimo["Funcionário"] if ultimo is not None else "JPaulo"
    combo_sugerido = ultimo["Combo"] if ultimo is not None and ultimo["Combo"] else ""

    conta = st.selectbox("Forma de Pagamento", list(dict.fromkeys([conta_sugerida] + contas_existentes + ["Carteira", "Nubank"])))
    combo = st.selectbox("Combo (opcional - use 'corte+barba')", [""] + list(dict.fromkeys([combo_sugerido] + combos_existentes)))

with col2:
    funcionario = st.selectbox(
        "Funcionário", ["JPaulo", "Vinicius"],
        index=["JPaulo", "Vinicius"].index(funcionario_sugerido) if funcionario_sugerido in ["JPaulo", "Vinicius"] else 0
    )
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])

fase = "Dono + funcionário"

# === PERÍODO (campo oficial) ===
periodo_opcao = st.selectbox("Período do Atendimento", ["Manhã", "Tarde", "Noite"])

# === CONTROLE DE ESTADO ===
if "combo_salvo" not in st.session_state:
    st.session_state.combo_salvo = False
if "simples_salvo" not in st.session_state:
    st.session_state.simples_salvo = False

if st.button("🧹 Limpar formulário"):
    st.session_state.combo_salvo = False
    st.session_state.simples_salvo = False
    st.rerun()

# === SALVAMENTO ===
def _preencher_fiado_vazio(linha: dict):
    """Garante chaves de fiado vazias para não quebrar a estrutura."""
    for c in COLS_FIADO:
        linha.setdefault(c, "")
    return linha

def salvar_combo(combo, valores_customizados):
    df, _ = carregar_base()
    servicos = combo.split("+")
    novas_linhas = []
    for servico in servicos:
        servico_formatado = servico.strip()
        valor = valores_customizados.get(servico_formatado, obter_valor_servico(servico_formatado))
        linha = {
            "Data": data,
            "Serviço": servico_formatado,
            "Valor": valor,
            "Conta": conta,
            "Cliente": cliente,
            "Combo": combo,
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Período": periodo_opcao,
        }
        novas_linhas.append(_preencher_fiado_vazio(linha))
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
        "Período": periodo_opcao,
    }
    nova_linha = _preencher_fiado_vazio(nova_linha)
    df_final = pd.concat([df, pd.DataFrame([nova_linha])], ignore_index=True)
    salvar_base(df_final)

# === FORMULÁRIO ===
if combo:
    st.subheader("💰 Edite os valores do combo antes de salvar:")
    valores_customizados = {}
    for servico in combo.split("+"):
        servico_formatado = servico.strip()
        valor_padrao = obter_valor_servico(servico_formatado)
        valor = st.number_input(
            f"{servico_formatado} (padrão: R$ {valor_padrao})",
            value=valor_padrao, step=1.0, key=f"valor_{servico_formatado}"
        )
        valores_customizados[servico_formatado] = valor

    if not st.session_state.combo_salvo:
        if st.button("✅ Confirmar e Salvar Combo"):
            duplicado = any(ja_existe_atendimento(cliente, data, s.strip(), combo) for s in combo.split("+"))
            if duplicado:
                st.warning("⚠️ Combo já registrado para este cliente e data.")
            else:
                salvar_combo(combo, valores_customizados)
                st.session_state.combo_salvo = True
                st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
    else:
        if st.button("➕ Novo Atendimento"):
            st.session_state.combo_salvo = False
            st.rerun()
else:
    st.subheader("✂️ Selecione o serviço e valor:")
    servico = st.selectbox("Serviço", servicos_existentes)
    valor_sugerido = obter_valor_servico(servico)
    valor = st.number_input("Valor", value=valor_sugerido, step=1.0)

    if not st.session_state.simples_salvo:
        if st.button("📁 Salvar Atendimento"):
            if ja_existe_atendimento(cliente, data, servico):
                st.warning("⚠️ Atendimento já registrado para este cliente, data e serviço.")
            else:
                salvar_simples(servico, valor)
                st.session_state.simples_salvo = True
                st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
    else:
        if st.button("➕ Novo Atendimento"):
            st.session_state.simples_salvo = False
            st.rerun()
