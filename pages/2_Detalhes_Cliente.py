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
from babel.dates import format_date  # meses pt-BR

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# === Função para formatar minutos como "Xh Ymin"
def formatar_tempo(minutos):
    if pd.isna(minutos) or minutos is None:
        return "Indisponível"
    try:
        minutos = int(minutos)
    except Exception:
        return "Indisponível"
    horas = minutos // 60
    resto = minutos % 60
    return f"{horas}h {resto}min" if horas > 0 else f"{resto} min"

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

    # Datas
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    # Duração (min) se não existir
    if "Duração (min)" not in df.columns or df["Duração (min)"].isna().all():
        if set(["Hora Chegada", "Hora Saída do Salão", "Hora Saída"]).intersection(df.columns):
            def calcular_duracao(row):
                try:
                    chegada = pd.to_datetime(row.get("Hora Chegada"), format="%H:%M:%S", errors="coerce")
                    saida_salao = pd.to_datetime(row.get("Hora Saída do Salão"), format="%H:%M:%S", errors="coerce")
                    saida_cadeira = pd.to_datetime(row.get("Hora Saída"), format="%H:%M:%S", errors="coerce")
                    fim = saida_salao if pd.notnull(saida_salao) else saida_cadeira
                    if pd.notnull(chegada) and pd.notnull(fim) and fim > chegada:
                        return (fim - chegada).total_seconds() / 60
                    return None
                except Exception:
                    return None
            df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

df = carregar_dados()

# === Sidebar: toggle para incluir fiado nos valores ===
st.sidebar.header("🎛️ Opções de cálculo")
st.sidebar.caption("Os gráficos e somatórios de VALOR consideram este ajuste.")
incluir_fiado = st.sidebar.toggle("Incluir **FIADO** nos gráficos de valor", value=False)

# === Base sem FIADO para cálculos de VALOR (padrão) ===
col_conta = next((c for c in df.columns
                  if c.strip().lower() in ["conta", "forma de pagamento", "pagamento", "status"]), None)

if col_conta:
    serie_conta = (
        df[col_conta]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    mask_fiado = serie_conta.eq("fiado")
else:
    mask_fiado = pd.Series(False, index=df.index)

# Decide a base de valores conforme o toggle
if incluir_fiado:
    df_valores = df.copy()
else:
    df_valores = df[~mask_fiado].copy()

df_valores["ValorNum"] = pd.to_numeric(df_valores["Valor"], errors="coerce").fillna(0)

# Badge de contexto
st.caption("🔎 Cálculo de valor atual: **{}**".format(
    "Inclui FIADO" if incluir_fiado else "Exclui FIADO"
))

# === Seleção do Cliente ===
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis,
                       index=clientes_disponiveis.index(cliente_default))

# === Mostrar imagem do cliente (clientes_status.Foto) ===
def buscar_link_foto(nome):
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet("clientes_status")
        df_status = get_as_dataframe(aba_status).dropna(how="all")
        df_status.columns = [str(col).strip() for col in df_status.columns]
        foto = df_status[df_status["Cliente"] == nome]["Foto"].dropna().values
        return foto[0] if len(foto) > 0 else None
    except Exception:
        return None

link_foto = buscar_link_foto(cliente)
if link_foto:
    try:
        response = requests.get(link_foto, timeout=8)
        img = Image.open(BytesIO(response.content))
        st.image(img, caption=cliente, width=200)
    except Exception:
        st.warning("Erro ao carregar imagem.")
else:
    st.info("Cliente sem imagem cadastrada.")

# === Dados do cliente (duas visões) ===
df_cliente = df[df["Cliente"] == cliente].copy()                     # histórico/frequência (inclui fiado)
df_cliente_val = df_valores[df_valores["Cliente"] == cliente].copy()  # valores (com/sem fiado conforme toggle)

# Aplicar tempo formatado
if "Duração (min)" in df_cliente.columns:
    df_cliente["Tempo Formatado"] = df_cliente["Duração (min)"].apply(formatar_tempo)

st.subheader(f"📅 Histórico de atendimentos - {cliente}")
colunas_exibir = ["Data_str", "Serviço", "Tipo", "Valor", "Funcionário", "Tempo Formatado"]
colunas_exibir = [col for col in colunas_exibir if col in df_cliente.columns]
st.dataframe(
    df_cliente.sort_values("Data", ascending=False)[colunas_exibir].rename(columns={"Data_str": "Data"}),
    use_container_width=True
)

# === Receita mensal (valor conforme toggle) ===
st.subheader("📊 Receita mensal")
if df_cliente_val.empty:
    st.info("Sem valores para exibir.")
else:
    df_cliente_val["Data_Ref_Mensal"] = df_cliente_val["Data"].dt.to_period("M").dt.to_timestamp()
    receita_mensal = df_cliente_val.groupby("Data_Ref_Mensal")["ValorNum"].sum().reset_index()
    receita_mensal["Mês_Ano"] = receita_mensal["Data_Ref_Mensal"].apply(
        lambda d: format_date(d, format="MMMM 'de' y", locale="pt_BR").capitalize()
    )
    receita_mensal["Valor_str"] = receita_mensal["ValorNum"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
    fig_receita = px.bar(
        receita_mensal,
        x="Mês_Ano",
        y="ValorNum",
        text="Valor_str",
        labels={"ValorNum": "Receita (R$)", "Mês_Ano": "Mês"},
        category_orders={"Mês_Ano": receita_mensal["Mês_Ano"].tolist()}
    )
    fig_receita.update_traces(textposition="inside")
    fig_receita.update_layout(height=400)
    st.plotly_chart(fig_receita, use_container_width=True)

# === Receita por Serviço e Produto (valor conforme toggle) ===
st.subheader("📊 Receita por Serviço e Produto")
if df_cliente_val.empty:
    st.info("Sem valores para exibir.")
else:
    df_tipos = df_cliente_val[["Serviço", "Tipo", "ValorNum"]].copy()
    receita_geral = (
        df_tipos.groupby(["Serviço", "Tipo"])["ValorNum"]
        .sum()
        .reset_index()
        .sort_values("ValorNum", ascending=False)
    )
    fig_receita_tipos = px.bar(
        receita_geral, x="Serviço", y="ValorNum", color="Tipo",
        text=receita_geral["ValorNum"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")),
        labels={"ValorNum": "Receita (R$)", "Serviço": "Item"}, barmode="group"
    )
    fig_receita_tipos.update_traces(textposition="outside")
    st.plotly_chart(fig_receita_tipos, use_container_width=True)

# === Atendimentos por Funcionário (histórico) ===
st.subheader("📊 Atendimentos por Funcionário")
atendimentos_unicos = df_cliente.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
atendimentos_por_funcionario = atendimentos_unicos["Funcionário"].value_counts().reset_index()
atendimentos_por_funcionario.columns = ["Funcionário", "Qtd Atendimentos"]
st.dataframe(atendimentos_por_funcionario, use_container_width=True)

# === Resumo por data (histórico) ===
st.subheader("📋 Resumo de Atendimentos")
df_cliente_dt = df[df["Cliente"] == cliente].copy()
resumo = df_cliente_dt.groupby("Data").agg(
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

# === Frequência de atendimento (histórico) ===
st.subheader("📈 Frequência de Atendimento")
data_corte = pd.to_datetime("2025-05-11")
df_antes = df_cliente_dt[df_cliente_dt["Data"] < data_corte].copy()
df_depois = df_cliente_dt[df_cliente_dt["Data"] >= data_corte].drop_duplicates(subset=["Data"]).copy()
df_freq = pd.concat([df_antes, df_depois]).sort_values("Data")
datas = df_freq["Data"].tolist()

if len(datas) < 2:
    st.info("Cliente possui apenas um atendimento.")
else:
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (pd.Timestamp.today().normalize() - ultimo_atendimento).days
    status = "🟢 Em dia" if dias_desde_ultimo <= media_freq else ("🟠 Pouco atrasado" if dias_desde_ultimo <= media_freq * 1.5 else "🔴 Muito atrasado")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Último Atendimento", ultimo_atendimento.strftime("%d/%m/%Y"))
    col2.metric("📊 Frequência Média", f"{media_freq:.1f} dias")
    col3.metric("⏱️ Desde Último", dias_desde_ultimo)
    col4.metric("📌 Status", status)

# === Insights do cliente ===
st.subheader("💡 Insights Adicionais")
meses_ativos = df_cliente["Mês_Ano"].nunique()
gasto_mensal_medio = (df_cliente_val["ValorNum"].sum() / meses_ativos) if meses_ativos > 0 else 0
status_vip = "Sim ⭐" if gasto_mensal_medio >= 70 else "Não"
mais_frequente = df_cliente["Funcionário"].mode()[0] if not df_cliente["Funcionário"].isna().all() else "Indefinido"
tempo_total = df_cliente["Duração (min)"].sum() if "Duração (min)" in df_cliente.columns else None
tempo_total_str = formatar_tempo(tempo_total)
ticket_medio = df_cliente_val["ValorNum"].mean() if not df_cliente_val.empty else 0
intervalo_medio = (sum([(datas[i] - datas[i-1]).days for i in range(1, len(datas))]) / len(datas[1:])) if len(datas) >= 2 else None

col5, col6, col7 = st.columns(3)
col5.metric("🏅 Cliente VIP", status_vip)
col6.metric("💇 Mais atendido por", mais_frequente)
col7.metric("🕒 Tempo Total no Salão", tempo_total_str)

col8, col9 = st.columns(2)
col8.metric("💸 Ticket Médio", f"R$ {ticket_medio:.2f}".replace(".", ","))
col9.metric("📆 Intervalo Médio", f"{intervalo_medio:.1f} dias" if intervalo_medio else "Indisponível")
