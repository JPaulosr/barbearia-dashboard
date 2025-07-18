import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("\U0001F3C6 Top 3 Clientes por Categoria")

# === GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"

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
    df = get_as_dataframe(planilha.worksheet(ABA_BASE)).dropna(how="all")
    df.columns = [c.strip() for c in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df = df.dropna(subset=["Cliente", "Funcionário"])
    df = df[df["Cliente"].str.lower().str.contains("boliviano|brasileiro|menino|sem preferencia|funcionário") == False]
    df = df[df["Cliente"].str.strip() != ""]
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    return df

@st.cache_data
def carregar_fotos():
    planilha = conectar_sheets()
    df_status = get_as_dataframe(planilha.worksheet(ABA_STATUS)).dropna(how="all")
    df_status.columns = [c.strip() for c in df_status.columns]
    return df_status[["Cliente", "Foto", "Família"]].dropna(subset=["Cliente"])

df = carregar_dados()
df_fotos = carregar_fotos()

# === Variável global para evitar duplicação de premiados ===
clientes_premiados = set()

# === Função de ranking ===
def gerar_top3(df_base, titulo, excluir_clientes=None):
    if excluir_clientes is None:
        excluir_clientes = set()

    col1, col2, col3 = st.columns([0.05, 0.15, 0.8])
    col1.markdown("### ")
    col2.markdown(f"#### {titulo}")

    df_base = df_base.copy()
    df_base["Valor"] = pd.to_numeric(df_base["Valor"], errors="coerce").fillna(0)

    # Agrupar por Cliente + Data
    valor_por_atendimento = df_base.groupby(["Cliente", "Data"], as_index=False)["Valor"].sum()

    # Total gasto por cliente
    total_gasto_por_cliente = valor_por_atendimento.groupby("Cliente")["Valor"].sum()

    # Ordenar, excluir premiados e pegar Top 3
    ranking = total_gasto_por_cliente.sort_values(ascending=False)
    ranking = ranking[~ranking.index.isin(excluir_clientes)]
    top3 = ranking.head(3).index.tolist()
    medalhas = ["🥇", "🥈", "🥉"]

    for i, cliente in enumerate(top3):
        clientes_premiados.add(cliente)
        atendimentos_unicos = valor_por_atendimento[valor_por_atendimento["Cliente"] == cliente]["Data"].nunique()

        linha = st.columns([0.05, 0.12, 0.83])
        linha[0].markdown(f"### {medalhas[i]}")

        link_foto = df_fotos[df_fotos["Cliente"] == cliente]["Foto"].dropna().values
        if len(link_foto):
            try:
                response = requests.get(link_foto[0])
                img = Image.open(BytesIO(response.content))
                linha[1].image(img, width=50)
            except:
                linha[1].text("[sem imagem]")
        else:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

        linha[2].markdown(f"**{cliente.lower()}** — {atendimentos_unicos} atendimentos")

# === Premiação ===
st.subheader("Top 3 Geral")
gerar_top3(df, "")

st.subheader("Top 3 JPaulo")
gerar_top3(df[df["Funcionário"] == "JPaulo"], "", excluir_clientes=clientes_premiados)

st.subheader("Top 3 Vinicius")
gerar_top3(df[df["Funcionário"] == "Vinicius"], "", excluir_clientes=clientes_premiados)

# === Cliente Família - Top 3 Grupos ===
# === Cliente Família - Top 3 Grupos com barra colorida ===
st.subheader("👨‍👩‍👧‍👦 Cliente Família — Top 3 Grupos")

# Junta dados com 'Família'
df_familia = df.merge(df_fotos[["Cliente", "Família"]], on="Cliente", how="left")
df_familia = df_familia[df_familia["Família"].notna() & (df_familia["Família"].str.strip() != "")]

# Remove atendimentos duplicados por cliente + data
atendimentos_unicos = df_familia.drop_duplicates(subset=["Cliente", "Data"])
atendimentos_unicos = atendimentos_unicos.merge(
    df_familia[["Cliente", "Família"]].drop_duplicates(), on="Cliente", how="left"
)

# Conta total de atendimentos únicos por família
familia_atendimentos = atendimentos_unicos.groupby("Família")["Data"].nunique().sort_values(ascending=False).head(3)

medalhas = ["🥇", "🥈", "🥉"]
cores = ["#FFD700", "#C0C0C0", "#CD7F32"]  # dourado, prata, bronze

max_atendimentos = familia_atendimentos.max()

for i, (familia, qtd_atendimentos) in enumerate(familia_atendimentos.items()):
    membros = df_fotos[df_fotos["Família"] == familia]
    qtd_membros = len(membros)

    nome_pai = familia.replace("Família ", "").strip().lower()
    nome_pai_formatado = nome_pai.capitalize()
    membro_foto = None

    # Tenta encontrar o cliente cujo nome seja exatamente igual ao nome do pai
    for idx, row in membros.iterrows():
        cliente_nome = str(row["Cliente"]).strip().lower()
        foto = row["Foto"]
        if cliente_nome == nome_pai and pd.notna(foto):
            membro_foto = foto
            break

    # Se não achou o pai, usa a primeira foto válida
    if not membro_foto and membros["Foto"].notna().any():
        membro_foto = membros["Foto"].dropna().values[0]

    linha = st.columns([0.05, 0.12, 0.83])
    linha[0].markdown(f"### {medalhas[i]}")

    if membro_foto:
        try:
            response = requests.get(membro_foto)
            img = Image.open(BytesIO(response.content))
            linha[1].image(img, width=50)
        except:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)
    else:
        linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

    # Texto e barra de progresso colorida
    texto = f"Família **{nome_pai_formatado}** — {qtd_atendimentos} atendimentos | {qtd_membros} membros"
    progresso_pct = int((qtd_atendimentos / max_atendimentos) * 100)
    cor_barra = cores[i]

    linha[2].markdown(texto)
    barra_html = f"""
    <div style="background-color:#333;border-radius:10px;height:14px;width:100%;margin-top:4px;margin-bottom:4px;">
      <div style="background-color:{cor_barra};width:{progresso_pct}%;height:100%;border-radius:10px;"></div>
    </div>
    <small style="color:gray;">{progresso_pct}% do líder</small>
    """
    linha[2].markdown(barra_html, unsafe_allow_html=True)
