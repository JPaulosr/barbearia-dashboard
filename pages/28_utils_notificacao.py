import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from PIL import Image
import requests
from io import BytesIO

# ====== TELEGRAM: tenta usar utils_notificacao.notificar; senão, fallback local ======
try:
    from utils_notificacao import notificar  # type: ignore
except Exception:
    def notificar(mensagem: str) -> bool:
        tg = st.secrets.get("TELEGRAM", {})
        token = tg.get("bot_token")
        chat_id = tg.get("chat_id")
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id,
            "text": mensagem,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=15)
            return r.ok
        except Exception:
            return False

st.set_page_config(layout="wide")
st.title("📅 Frequência dos Clientes")

# === CONFIG GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === AUTO NOTIFY (padrões podem ser trocados no secrets) ===
AUTO_CFG = st.secrets.get("AUTO_NOTIFY", {})
AUTO_DEFAULT = bool(AUTO_CFG.get("enabled", True))
DAILY_ONCE = bool(AUTO_CFG.get("daily_once", True))

# === LOGO PADRÃO ===
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752708088/Imagem_do_WhatsApp_de_2025-07-16_%C3%A0_s_11.20.50_cbeb2873_nlhddx.jpg"

# === Funções auxiliares ===
def carregar_imagem(link):
    url = link if link and isinstance(link, str) and link.startswith("http") else LOGO_PADRAO
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
        else:
            st.warning(f"🔗 Erro ao carregar imagem ({response.status_code}): {url}")
    except Exception as e:
        st.error(f"❌ Erro ao carregar imagem: {e}")
    return None

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

@st.cache_data
def carregar_status():
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet(STATUS_ABA)
        status = get_as_dataframe(aba_status).dropna(how="all")
        status.columns = [str(col).strip() for col in status.columns]

        colunas = status.columns.tolist()
        coluna_imagem = next((col for col in colunas if col.strip().lower() in ["linkimagem", "imagem cliente", "foto", "imagem"]), None)

        if coluna_imagem:
            status = status.rename(columns={coluna_imagem: "Imagem"})
        else:
            status["Imagem"] = ""

        status["Imagem"] = status["Imagem"].fillna("").str.strip()
        return status[["Cliente", "Status", "Imagem"]]
    except Exception:
        return pd.DataFrame(columns=["Cliente", "Status", "Imagem"])

# === PRÉ-PROCESSAMENTO ===
df = carregar_dados()
df_status = carregar_status()

# Filtra apenas clientes ativos
df_status = df_status[df_status["Status"] == "Ativo"]
clientes_ativos = df_status["Cliente"].unique().tolist()

df = df[df["Cliente"].isin(clientes_ativos)]
atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

# === CÁLCULO DE FREQUÊNCIA ===
frequencia_clientes = []
hoje = pd.Timestamp.today().normalize()

for cliente, grupo in atendimentos.groupby("Cliente"):
    datas = grupo.sort_values("Data")["Data"].tolist()
    if len(datas) < 2:
        continue
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (hoje - ultimo_atendimento).days

    if dias_desde_ultimo <= media_freq:
        status = ("🟢 Em dia", "Em dia")
    elif dias_desde_ultimo <= media_freq * 1.5:
        status = ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        status = ("🔴 Muito atrasado", "Muito atrasado")

    frequencia_clientes.append({
        "Status": status[0],
        "Cliente": cliente,
        "Último Atendimento": ultimo_atendimento.date(),
        "Qtd Atendimentos": len(datas),
        "Frequência Média (dias)": round(media_freq, 1),
        "Dias Desde Último": dias_desde_ultimo,
        "Status_Label": status[1]
    })

freq_df = pd.DataFrame(frequencia_clientes)
freq_df = freq_df.merge(df_status[["Cliente", "Imagem"]], on="Cliente", how="left")

# === INDICADORES ===
st.markdown("### 📊 Indicadores")
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Clientes ativos", freq_df["Cliente"].nunique())
col2.metric("🟢 Em dia", freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique())
col3.metric("🟠 Pouco atrasado", freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique())
col4.metric("🔴 Muito atrasado", freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique())

# ======= SIDEBAR: Auto Notificações =======
st.sidebar.header("🔔 Notificações")
auto_on = st.sidebar.toggle("⚡ Enviar automaticamente", value=AUTO_DEFAULT,
                            help="Envia resumo e listas automaticamente ao abrir a página.")
st.sidebar.caption("Cada tipo de mensagem é enviado no máximo 1x por dia.")

def already_sent(kind: str) -> bool:
    """Controle simples para não enviar mais de 1x por dia por tipo."""
    key = f"sent_{kind}_{pd.Timestamp.today().date().isoformat()}"
    return st.session_state.get(key, False)

def mark_sent(kind: str):
    key = f"sent_{kind}_{pd.Timestamp.today().date().isoformat()}"
    st.session_state[key] = True

def enviar_resumo():
    tot = freq_df["Cliente"].nunique()
    n_ok = freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique()
    n_pouco = freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique()
    n_muito = freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique()
    msg = (
        "*📊 Relatório de Frequência*\n"
        f"👥 Ativos: *{tot}*\n"
        f"🟢 Em dia: *{n_ok}*\n"
        f"🟠 Pouco atrasado: *{n_pouco}*\n"
        f"🔴 Muito atrasado: *{n_muito}*"
    )
    return notificar(msg)

def enviar_lista(df_list, titulo_emoji):
    if df_list.empty:
        return False
    nomes = "\n".join([f"- {n}" for n in df_list["Cliente"].tolist()])
    msg = f"*{titulo_emoji}*\n{nomes}"
    return notificar(msg)

# Botões manuais (mantidos como fallback)
if st.sidebar.button("Enviar resumo agora"):
    ok = enviar_resumo()
    st.sidebar.success("Resumo enviado!") if ok else st.sidebar.error("Falha.")

colA, colB = st.sidebar.columns(2)
with colA:
    if st.button("Pouco atrasados"):
        ok = enviar_lista(freq_df[freq_df["Status_Label"] == "Pouco atrasado"][["Cliente"]], "🟠 Pouco atrasados")
        st.success("Enviado!") if ok else st.error("Falha.")
with colB:
    if st.button("Muito atrasados"):
        ok = enviar_lista(freq_df[freq_df["Status_Label"] == "Muito atrasados"][["Cliente"]], "🔴 Muito atrasados")
        st.success("Enviado!") if ok else st.error("Falha.")

# ======= Envio AUTOMÁTICO no carregamento =======
if auto_on:
    # Resumo geral
    if not (DAILY_ONCE and already_sent("resumo")):
        if enviar_resumo():
            mark_sent("resumo")
    # Pouco atrasados
    df_pouco = freq_df[freq_df["Status_Label"] == "Pouco atrasado"][["Cliente"]]
    if not (DAILY_ONCE and already_sent("pouco")) and not df_pouco.empty:
        if enviar_lista(df_pouco, "🟠 Pouco atrasados"):
            mark_sent("pouco")
    # Muito atrasados
    df_muito = freq_df[freq_df["Status_Label"] == "Muito atrasado"][["Cliente"]]
    if not (DAILY_ONCE and already_sent("muito")) and not df_muito.empty:
        if enviar_lista(df_muito, "🔴 Muito atrasados"):
            mark_sent("muito")

# === GALERIA (mantida, sem botões por cliente para evitar duplicidade) ===
def exibir_clientes_em_galeria(df_input, titulo):
    import re
    st.markdown(titulo)

    nome_filtrado = st.text_input(
        f"🔍 Filtrar {titulo.replace('#', '').strip()} por nome",
        key=f"filtro-{titulo}"
    ).strip().lower()

    if nome_filtrado:
        df_input = df_input[df_input["Cliente"].str.lower().str.contains(nome_filtrado)]

    if df_input.empty:
        st.warning("Nenhum cliente encontrado com esse filtro.")
        return

    colunas = st.columns(3)

    for idx, (_, row) in enumerate(df_input.iterrows()):
        col = colunas[idx % 3]
        with col:
            st.markdown("----")
            imagem = carregar_imagem(row.get("Imagem", ""))
            if imagem:
                st.image(imagem, width=80)
            st.markdown(f"**{row['Cliente']}**")

            try:
                data_formatada = pd.to_datetime(row["Último Atendimento"]).strftime("%d/%m/%Y")
            except Exception:
                data_formatada = row["Último Atendimento"]

            st.markdown(
                f"🗓️ Último: {data_formatada}  \n"
                f"🔁 Freq: {row['Frequência Média (dias)']}d  \n"
                f"⏳ {row['Dias Desde Último']} dias sem vir"
            )

# === EXIBIÇÃO FINAL COM NOVO LAYOUT ===
st.divider()
exibir_clientes_em_galeria(freq_df[freq_df["Status_Label"] == "Muito atrasado"], "## 🔴 Muito Atrasados")

st.divider()
exibir_clientes_em_galeria(freq_df[freq_df["Status_Label"] == "Pouco atrasado"], "## 🟠 Pouco Atrasados")

st.divider()
exibir_clientes_em_galeria(freq_df[freq_df["Status_Label"] == "Em dia"], "## 🟢 Em Dia")
