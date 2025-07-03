import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

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
    df = df[df["Data"] >= pd.to_datetime("2025-05-01")]  # restringe a partir de maio de 2025
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    if "Duração (min)" not in df.columns or df["Duração (min)"].isna().all():
        if set(["Hora Chegada", "Hora Saída do Salão"]).issubset(df.columns):
            def calcular_duracao(row):
                try:
                    h1 = pd.to_datetime(row["Hora Chegada"], format="%H:%M:%S")
                    h2 = pd.to_datetime(row["Hora Saída do Salão"], format="%H:%M:%S")
                    return (h2 - h1).total_seconds() / 60 if h2 > h1 else None
                except:
                    return None
            df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

df = carregar_dados()

clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente = st.selectbox("🔍 Selecione o cliente para detalhamento:", options=[""] + clientes_disponiveis, index=0)

# === Filtro de mês ===
meses_disponiveis = sorted(df["Mês_Ano"].unique())
mes_selecionado = st.selectbox("📅 Filtrar por mês:", ["Todos"] + meses_disponiveis)

if cliente:
    df_cliente = df[df["Cliente"].str.lower() == cliente.lower()].copy()
    if mes_selecionado != "Todos":
        df_cliente = df_cliente[df_cliente["Mês_Ano"] == mes_selecionado]

    if df_cliente.empty:
        st.warning("Nenhum dado encontrado para esse cliente no período selecionado.")
    else:
        def buscar_link_foto(nome):
            try:
                planilha = conectar_sheets()
                aba_status = planilha.worksheet("clientes_status")
                df_status = get_as_dataframe(aba_status).dropna(how="all")
                df_status.columns = [str(col).strip() for col in df_status.columns]
                foto = df_status[df_status["Cliente"] == nome]["Foto"].dropna().values
                return foto[0] if len(foto) > 0 else None
            except:
                return None

        link_foto = buscar_link_foto(cliente)
        if link_foto:
            try:
                response = requests.get(link_foto)
                img = Image.open(BytesIO(response.content))
                st.image(img, caption=f"{cliente}", width=200)
            except:
                st.warning("Erro ao carregar imagem do cliente.")
        else:
            st.info("Cliente sem imagem cadastrada.")

        st.subheader(f"📅 Histórico de atendimentos - {cliente}")
        st.dataframe(df_cliente.sort_values("Data", ascending=False).drop(columns=["Data"]).rename(columns={"Data_str": "Data"}), use_container_width=True)

        st.subheader("📋 Resumo de Atendimentos")
        resumo = df_cliente.groupby("Data").agg(
            Qtd_Serviços=("Serviço", "count"),
            Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum())
        ).reset_index()
        resumo["Qtd_Combo"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
        resumo["Qtd_Simples"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)
        resumo_final = pd.DataFrame({
            "Total Atendimentos": [resumo.shape[0]],
            "Qtd Combos": [resumo["Qtd_Combo"].sum()],
            "Qtd Simples": [resumo["Qtd_Simples"].sum()]
        })
        st.dataframe(resumo_final, use_container_width=True)

        st.subheader("📈 Frequência de Atendimento")
        df_freq = df_cliente.drop_duplicates(subset=["Data"]).sort_values("Data")
        datas = df_freq["Data"].tolist()
        if len(datas) >= 2:
            diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
            media_freq = sum(diffs) / len(diffs)
            ultimo_atendimento = datas[-1]
            dias_desde_ultimo = (pd.Timestamp.today().normalize() - ultimo_atendimento).days
            status = "🟢 Em dia" if dias_desde_ultimo <= media_freq else ("🟠 Pouco atrasado" if dias_desde_ultimo <= media_freq * 1.5 else "🔴 Muito atrasado")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📅 Último Atendimento", ultimo_atendimento.strftime("%d/%m/%Y"))
            col2.metric("📊 Frequência Média", f"{media_freq:.1f} dias")
            col3.metric("⏱️ Dias Desde Último", dias_desde_ultimo)
            col4.metric("📌 Status", status)
        else:
            st.info("Cliente possui apenas um atendimento. Frequência não aplicável.")

        st.subheader("💡 Insights Adicionais do Cliente")
        meses_ativos = df_cliente["Mês_Ano"].nunique()
        gasto_mensal_medio = df_cliente["Valor"].sum() / meses_ativos if meses_ativos > 0 else 0
        status_vip = "Sim ⭐" if gasto_mensal_medio >= 70 else "Não"
        mais_frequente = df_cliente["Funcionário"].mode()[0] if not df_cliente["Funcionário"].isna().all() else "Indefinido"
        tempo_total = df_cliente["Duração (min)"].sum() if "Duração (min)" in df_cliente.columns else None
        tempo_total_str = f"{int(tempo_total)} minutos" if tempo_total else "Indisponível"
        ticket_medio = df_cliente["Valor"].mean()
        intervalo_medio = media_freq if len(datas) >= 2 else None
        col5, col6, col7 = st.columns(3)
        col5.metric("🏅 Cliente VIP", status_vip)
        col6.metric("💇 Mais atendido por", mais_frequente)
        col7.metric("🕒 Tempo Total no Salão", tempo_total_str)
        col8, col9 = st.columns(2)
        col8.metric("💸 Ticket Médio", f"R$ {ticket_medio:.2f}".replace(".", ","))
        col9.metric("📆 Intervalo Médio", f"{intervalo_medio:.1f} dias" if intervalo_medio else "Indisponível")
else:
    st.info("Selecione um cliente para visualizar os dados.")
