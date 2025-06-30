import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime

# Função para carregar os dados do Google Sheets
def carregar_dados_google_sheets():
    escopo = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    path = 'credenciais.json'  # Arquivo da conta de serviço
    
    credenciais = service_account.Credentials.from_service_account_file(path, scopes=escopo)
    service = build('sheets', 'v4', credentials=credenciais)

    # Planilha e abas
    ID = '1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE'
    abas = ['Base de Dados']
    aba = abas[0]

    sheet = service.spreadsheets()
    resultado = sheet.values().get(spreadsheetId=ID, range=f"{aba}!A1:Z10000").execute()
    valores = resultado.get('values', [])
    df = pd.DataFrame(valores[1:], columns=valores[0])

    # Conversões necessárias
    df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    df['Data_str'] = df['Data'].dt.strftime('%d/%m/%Y')

    for col in ['Chegada', 'Início', 'Saída']:
        df[col] = pd.to_datetime(df[col], format='%H:%M', errors='coerce')

    df['Tempo_espera'] = (df['Início'] - df['Chegada']).dt.total_seconds() / 60
    df['Tempo_total'] = (df['Saída'] - df['Chegada']).dt.total_seconds() / 60
    df['Duração'] = (df['Saída'] - df['Início']).dt.total_seconds() / 60
    df['Duração formatada'] = df['Duração'].apply(lambda x: f"{int(x//60)}h {int(x%60):02d}min" if pd.notnull(x) else '-')

    return df

# ================= TÍTULO =====================
st.title("\U000023F1 Tempos por Atendimento")

# ================= CARREGA DADOS =====================
df = carregar_dados_google_sheets()
st.write(f"_Registros carregados: {len(df)}_")

# ================= FILTROS =====================
st.subheader("\U0001F5C2 Filtros")

col1, col2, col3 = st.columns([3, 3, 4])

funcionarios = df['Funcionário'].dropna().unique().tolist()
with col1:
    filtro_func = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)

with col2:
    filtro_cliente = st.text_input("Buscar Cliente")

with col3:
    data_min = df['Data'].min()
    data_max = df['Data'].max()
    periodo = st.date_input("Período", value=(data_min, data_max))

# ================= APLICA FILTROS =====================
df_filtrado = df.copy()
if filtro_func:
    df_filtrado = df_filtrado[df_filtrado['Funcionário'].isin(filtro_func)]

if filtro_cliente:
    df_filtrado = df_filtrado[df_filtrado['Cliente'].str.contains(filtro_cliente, case=False, na=False)]

if isinstance(periodo, tuple) and len(periodo) == 2:
    ini, fim = periodo
    df_filtrado = df_filtrado[(df_filtrado['Data'] >= pd.to_datetime(ini)) & (df_filtrado['Data'] <= pd.to_datetime(fim))]

# ================= RANKINGS =====================
st.subheader("\U0001F3C6 Rankings de Tempo por Atendimento")

col1, col2 = st.columns(2)

mais_rapidos = df_filtrado.sort_values(by='Duração').head(5)
mais_lentos = df_filtrado.sort_values(by='Duração', ascending=False).head(5)

with col1:
    st.markdown("**Mais Rápidos**")
    st.dataframe(mais_rapidos[['Data_str', 'Cliente', 'Funcionário', 'Tipo', 'Duração formatada']])

with col2:
    st.markdown("**Mais Lentos**")
    st.dataframe(mais_lentos[['Data_str', 'Cliente', 'Funcionário', 'Tipo', 'Duração formatada']])

# ================= TEMPO MÉDIO POR SERVIÇO =====================
st.subheader("\U0001F4C8 Tempo Médio por Tipo de Serviço")

media_por_servico = df_filtrado.groupby('Tipo')['Duração'].mean().dropna().sort_values()
fig = px.bar(
    media_por_servico,
    x=media_por_servico.index,
    y=media_por_servico.values,
    labels={'x': 'Tipo de Serviço', 'y': 'Duração Média (min)'}
)
fig.update_traces(marker_color='lightskyblue')
st.plotly_chart(fig, use_container_width=True)

# ================= MAIORES TEMPOS DE ESPERA =====================
st.subheader("\U0001F4C5 Dias com Maior Tempo Médio de Atendimento")

media_por_dia = df_filtrado.groupby('Data')['Tempo_espera'].mean().dropna().sort_values(ascending=False).head(10)

if not media_por_dia.empty:
    fig2 = px.bar(
        media_por_dia,
        x=media_por_dia.index,
        y=media_por_dia.values,
        labels={'x': 'Data', 'y': 'Espera (min)'},
        title="Top 10 Dias com Maior Tempo de Espera"
    )
    fig2.update_traces(marker_color='lightskyblue')
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("Nenhum dado disponível para gerar o gráfico.")
