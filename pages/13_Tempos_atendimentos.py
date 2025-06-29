import streamlit as st
import pandas as pd
import plotly.express as px
from utils import carregar_dados_google_sheets

st.set_page_config("Tempos por Atendimento", layout="wide")
st.title("⏱️ Tempos por Atendimento")

# Carrega os dados
df = carregar_dados_google_sheets()

# Converte colunas de horário
df['Hora Chegada'] = pd.to_datetime(df['Hora Chegada'], errors='coerce').dt.time
df['Hora Início'] = pd.to_datetime(df['Hora Início'], errors='coerce').dt.time
df['Hora Saída'] = pd.to_datetime(df['Hora Saída'], errors='coerce').dt.time
df['Data'] = pd.to_datetime(df['Data'], errors='coerce')

# Remove linhas sem hora de início
mask_hora = df['Hora Início'].notna()
df = df[mask_hora].copy()

# Calcula tempos em minutos
def calcular_tempo(row):
    try:
        chegada = pd.to_datetime(str(row['Data'].date()) + ' ' + str(row['Hora Chegada']))
        inicio = pd.to_datetime(str(row['Data'].date()) + ' ' + str(row['Hora Início']))
        saida = pd.to_datetime(str(row['Data'].date()) + ' ' + str(row['Hora Saída']))

        espera = (inicio - chegada).total_seconds() / 60 if pd.notnull(chegada) else 0
        atendimento = (saida - inicio).total_seconds() / 60 if pd.notnull(saida) else 0
        total = (saida - chegada).total_seconds() / 60 if pd.notnull(chegada) and pd.notnull(saida) else 0
        return pd.Series([espera, atendimento, total])
    except:
        return pd.Series([0, 0, 0])

df[['Espera (min)', 'Atendimento (min)', 'Tempo Total (min)']] = df.apply(calcular_tempo, axis=1)

# Sidebar - Seleciona data
data_unicas = df['Data'].dt.date.unique()
data_sel = st.sidebar.date_input("Selecionar data", value=max(data_unicas))
df_dia = df[df['Data'].dt.date == data_sel]

# ================== Indicadores =====================
st.subheader(f"📊 Indicadores do dia {data_sel.strftime('%d/%m/%Y')}")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", len(df_dia))
col2.metric("Média de Espera", round(df_dia['Espera (min)'].mean(), 1) if not df_dia.empty else '-')
col3.metric("Média Atendimento", round(df_dia['Atendimento (min)'].mean(), 1) if not df_dia.empty else '-')
col4.metric("Tempo Total Médio", round(df_dia['Tempo Total (min)'].mean(), 1) if not df_dia.empty else '-')

# ================== Gráfico - Espera por Cliente =====================
st.markdown("""
### 🕓 Gráfico - Tempo de Espera por Cliente
""")
if not df_dia.empty:
    fig_espera = px.bar(df_dia, x='Cliente', y='Espera (min)', color='Cliente', title='Tempo de espera por cliente')
    st.plotly_chart(fig_espera, use_container_width=True)
else:
    st.info("Nenhum atendimento registrado nesta data.")

# ================== Ranking de Atendimento =====================
st.markdown("""
### 🏆 Ranking de Atendimentos
""")
col_fast, col_slow = st.columns(2)
col_fast.write("#### Mais Rápidos")
col_fast.dataframe(df_dia.sort_values(by='Tempo Total (min)').head(10)[['Cliente', 'Tempo Total (min)', 'Tipo']])
col_slow.write("#### Mais Lentos")
col_slow.dataframe(df_dia.sort_values(by='Tempo Total (min)', ascending=False).head(10)[['Cliente', 'Tempo Total (min)', 'Tipo']])

# ================== Tempo médio por tipo de serviço =====================
st.markdown("""
### 📈 Tempo Médio por Tipo de Serviço
""")
if 'Tipo' in df_dia.columns:
    df_tipo = df_dia.groupby('Tipo')[['Espera (min)', 'Atendimento (min)']].mean().reset_index()
    fig_tipo = px.bar(df_tipo, x='Tipo', y=['Espera (min)', 'Atendimento (min)'], barmode='group', title='Tempo médio por tipo de serviço')
    st.plotly_chart(fig_tipo, use_container_width=True)

# ================== Dias com maior espera =====================
st.markdown("""
### 📅 Dias com Maior Espera Média
""")
df_dias = df.groupby(df['Data'].dt.date)['Espera (min)'].mean().reset_index()
df_dias.columns = ['Data', 'Média de Espera']
fig_dias = px.line(df_dias, x='Data', y='Média de Espera', title='Evolução da espera média por dia')
st.plotly_chart(fig_dias, use_container_width=True)

# ================== Faixas de Tempo Total =====================
st.markdown("""
### ⏳ Distribuição por Faixa de Tempo Total
""")
bins = [0, 15, 30, 45, 60, 90, 120, 1000]
labels = ['0-15min', '15-30min', '30-45min', '45-60min', '1h-1h30', '1h30-2h', '2h+']
df['Faixa'] = pd.cut(df['Tempo Total (min)'], bins=bins, labels=labels)
fig_faixas = px.histogram(df, x='Faixa', title='Quantidade de atendimentos por faixa de tempo total')
st.plotly_chart(fig_faixas, use_container_width=True)

# ================== Tabela Final =====================
st.markdown("""
### 📋 Atendimentos do Dia
""")
colunas_final = ['Cliente', 'Funcionário', 'Hora Chegada', 'Hora Início', 'Hora Saída', 'Espera (min)', 'Atendimento (min)', 'Tempo Total (min)', 'Tipo']
st.dataframe(df_dia[colunas_final].sort_values(by='Hora Início'))
