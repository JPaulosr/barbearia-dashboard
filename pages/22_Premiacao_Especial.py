import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("🏆 Premiação Especial - Destaques do Ano")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

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
    aba = planilha.worksheet("Base de Dados")
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

@st.cache_data
def carregar_status():
    planilha = conectar_sheets()
    aba = planilha.worksheet("clientes_status")
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df

def limpar_nomes(nome):
    nome = str(nome).strip().lower()
    nomes_excluir = ["boliviano", "brasileiro", "menino", "sem nome", "cliente", "sem preferência", "sem preferencia"]
    return not any(gen in nome for gen in nomes_excluir)

def mostrar_cliente(nome, legenda):
    foto = df_status[df_status["Cliente"] == nome]["Foto"].dropna().values
    col1, col2 = st.columns([1, 5])
    with col1:
        if len(foto) > 0:
            try:
                response = requests.get(foto[0])
                img = Image.open(BytesIO(response.content))
                st.image(img, width=100)
            except:
                st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=100)
        else:
            st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=100)
    with col2:
        st.markdown(f"### 🏅 {nome.title()}")
        st.markdown(legenda)

df = carregar_dados()
df_status = carregar_status()
df = df[df["Cliente"].notna() & df["Cliente"].apply(limpar_nomes)]
df = df[df["Valor"] > 0]

# 🎯 Cliente Mais Fiel
st.subheader("🎯 Cliente Mais Fiel")
clientes_fieis = df.groupby("Cliente")["Data"].apply(lambda x: x.dt.to_period("M").nunique()).sort_values(ascending=False).head(1)
for cliente, meses in clientes_fieis.items():
    mostrar_cliente(cliente, f"Participou em **{meses} meses diferentes**!")

# 🧼 Cliente Combo
st.subheader("🧼 Cliente Combo")
df_combo = df.copy()
df_combo["Dia"] = df_combo["Data"].dt.date
combos = df_combo.groupby(["Cliente", "Dia"]).size().reset_index(name="Qtd")
combos = combos[combos["Qtd"] > 1]
combo_count = combos.groupby("Cliente")["Dia"].count().sort_values(ascending=False).head(1)
for cliente, qtd in combo_count.items():
    mostrar_cliente(cliente, f"Fez **{qtd} atendimentos com combos**!")

# 📅 Cliente Frequente
st.subheader("📅 Cliente Frequente")
freq_resultados = []
for nome, grupo in df.groupby("Cliente"):
    datas = sorted(grupo["Data"].drop_duplicates())
    if len(datas) >= 2:
        intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, len(datas))]
        media_dias = sum(intervalos) / len(intervalos)
        freq_resultados.append((nome, media_dias))
df_freq = pd.DataFrame(freq_resultados, columns=["Cliente", "Frequência Média"]).sort_values("Frequência Média").head(1)
for _, row in df_freq.iterrows():
    mostrar_cliente(row["Cliente"], f"Retornava em média a cada **{row['Frequência Média']:.1f} dias**.")

# 🛍️ Cliente Mais Variado
st.subheader("🛍️ Cliente Mais Variado")
servicos_var = df.groupby("Cliente")["Serviço"].nunique().sort_values(ascending=False).head(1)
for cliente, qtd in servicos_var.items():
    mostrar_cliente(cliente, f"Usou **{qtd} tipos diferentes de serviços**.")

# 👨‍👩‍👧‍👦 Cliente Família
st.subheader("👨‍👩‍👧‍👦 Cliente Família")
df_familia = df.merge(df_status[["Cliente", "Família"]], on="Cliente", how="left")
df_familia = df_familia[df_familia["Família"].notna() & (df_familia["Família"] != "")]

if not df_familia.empty:
    # Calcular o total gasto por família
    gasto_total = df_familia.groupby("Família")["Valor"].sum().sort_values(ascending=False)
    familia_top = gasto_total.index[0]
    total_gasto = gasto_total.iloc[0]

    # Filtrar só os atendimentos da família vencedora
    df_top = df_familia[df_familia["Família"] == familia_top].copy()

    # Corrigir a contagem de atendimentos com a lógica oficial
    df_top["Data"] = pd.to_datetime(df_top["Data"])
    df_top["Data_Agrupamento"] = df_top["Data"]
    corte = pd.to_datetime("2025-05-11")
    df_top["Data_Agrupamento"] = df_top.apply(
        lambda row: f"{row['Cliente']}_{row['Data'].date()}" if row["Data"] >= corte else row.name,
        axis=1
    )
    total_atendimentos = df_top["Data_Agrupamento"].nunique()
    total_dias = df_top["Data"].dt.date.nunique()
    membros_df = df_status[df_status["Família"] == familia_top]

    st.markdown(f"### 🏅 Família {familia_top.title()}")
    st.markdown(
        f"Família **{familia_top.lower()}** teve atendimentos em **{total_dias} dias diferentes**, "
        f"somando **{total_atendimentos} atendimentos individuais** e **R$ {total_gasto:.2f}** gastos entre todos os membros."
    )

    for _, row in membros_df.iterrows():
        col1, col2 = st.columns([1, 5])
        with col1:
            try:
                if pd.notna(row["Foto"]):
                    response = requests.get(row["Foto"])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, width=100)
                else:
                    raise Exception("sem imagem")
            except:
                st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=100)
        with col2:
            st.markdown(f"**{row['Cliente']}**")
else:
    st.info("Nenhuma família com atendimentos foi encontrada.")


# 🗓️ Cliente do Mês
st.subheader("🗓️ Cliente do Mês")
mes_atual = pd.Timestamp.now().month
ano_atual = pd.Timestamp.now().year
df_mes = df[(df["Data"].dt.month == mes_atual) & (df["Data"].dt.year == ano_atual)]
cliente_mes = df_mes["Cliente"].value_counts().head(1)

if not df_mes.empty and not cliente_mes.empty:
    for cliente, qtd in cliente_mes.items():
        valor_total = df_mes[df_mes["Cliente"] == cliente]["Valor"].sum()
        mostrar_cliente(cliente, f"Fez **{qtd} atendimentos** no mês atual, com **R$ {valor_total:.2f} gastos**.")
else:
    st.info("Nenhum cliente válido encontrado neste mês.")

# ✨ Cliente Revelação
st.subheader("✨ Cliente Revelação")
data_corte = pd.to_datetime("2025-01-01")
recentes = df[df["Data"] >= data_corte]
novatos = recentes.groupby("Cliente")["Data"].nunique().sort_values(ascending=False).head(1)
for cliente, dias in novatos.items():
    mostrar_cliente(cliente, f"Novo cliente com **{dias} visitas recentes** desde 2025.")
