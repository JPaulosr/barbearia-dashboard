import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import pytz
from google.oauth2 import service_account
import gspread

st.set_page_config(page_title="Tempos por Atendimento", layout="wide")

# Função para carregar os dados diretamente do Google Sheets
def carregar_dados_google_sheets():
    url_planilha = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
    path = "creds.json"

    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = service_account.Credentials.from_service_account_file(path, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_url(url_planilha)

    base = planilha.worksheet("Base de Dados")
    dados = base.get_all_records()
    df = pd.DataFrame(dados)

    df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    df['Chegada'] = pd.to_datetime(df['Chegada'], errors='coerce')
    df['Saída'] = pd.to_datetime(df['Saída'], errors='coerce')
    df['Início'] = pd.to_datetime(df['Início'], errors='coerce')
    df['Duração (min)'] = (df['Saída'] - df['Início']).dt.total_seconds() / 60
    df['Espera (min)'] = (df['Início'] - df['Chegada']).dt.total_seconds() / 60

    df = df[df['Data'].notna()]
    df['Data_str'] = df['Data'].dt.strftime('%d/%m/%Y')

    return df

# Carregar dados
df = carregar_dados_google_sheets()
st.title("\ud83d\udd70\ufe0f Tempos por Atendimento")
st.markdown(f"<i>Registros carregados: {len(df)}</i>", unsafe_allow_html=True)

# Filtros
st.subheader("\ud83d\udecb\ufe0f Filtros")
col1, col2, col3 = st.columns([3, 3, 3])

with col1:
    funcionarios = st.multiselect("Filtrar por Funcionário", options=sorted(df['Funcionário'].dropna().unique()), default=sorted(df['Funcionário'].dropna().unique()))
with col2:
    cliente_nome = st.text_input("Buscar Cliente")
with col3:
    data_intervalo = st.date_input("Período", [])

# Aplicar filtros
if funcionarios:
    df = df[df['Funcionário'].isin(funcionarios)]
if cliente_nome:
    df = df[df['Cliente'].str.contains(cliente_nome, case=False, na=False)]
if len(data_intervalo) == 2:
    df = df[(df['Data'] >= pd.to_datetime(data_intervalo[0])) & (df['Data'] <= pd.to_datetime(data_intervalo[1]))]

# --- GRÁFICO: Dias com Maior Tempo Médio ---
st.subheader("\ud83d\uddd3\ufe0f Dias com Maior Tempo Médio de Atendimento")
df_validos = df[df['Duração (min)'].notnull() & df['Duração (min)'] > 0]

dias_lentos = (
    df_validos.groupby('Data')['Duração (min)']
    .mean()
    .sort_values(ascending=False)
    .head(10)
    .reset_index()
)

fig_dias_lentos = px.bar(dias_lentos, x='Data', y='Duração (min)',
                         labels={'Data': 'Data', 'Duração (min)': 'Duração Média (min)'},
                         title='Top 10 Dias com Maior Tempo de Atendimento',
                         color_discrete_sequence=['skyblue'])
fig_dias_lentos.update_layout(xaxis_title="Data", yaxis_title="Tempo (min)", title_x=0.5)

st.plotly_chart(fig_dias_lentos, use_container_width=True)
