import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import requests
from io import BytesIO

st.set_page_config(page_title="Detalhes do Cliente", layout="wide")

# Função para converter minutos para "Xh Ymin"
def formatar_tempo(minutos):
    if pd.isna(minutos):
        return "Indisponível"
    horas = int(minutos) // 60
    minutos_restantes = int(minutos) % 60
    if horas == 0:
        return f"{minutos_restantes} min"
    else:
        return f"{horas}h {minutos_restantes}min"

# Função para carregar dados da planilha
@st.cache_data
def carregar_dados():
    url = 'https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/export?format=csv&gid=0'
    df = pd.read_csv(url)
    df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
    return df

# Função para carregar imagens da aba clientes_status
@st.cache_data
def carregar_status_clientes():
    url = 'https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/export?format=csv&gid=1247499474'
    df = pd.read_csv(url)
    return df

# Carregar dados
df = carregar_dados()
status_df = carregar_status_clientes()

st.markdown("## 📌 Detalhamento do Cliente")

# Seleção do cliente
clientes = df['Cliente'].dropna().unique()
cliente_selecionado = st.selectbox("👤 Selecione o cliente para detalhamento", sorted(clientes))

# Verificar se cliente foi selecionado
if cliente_selecionado:
    dados_cliente = df[df['Cliente'] == cliente_selecionado].copy()
    dados_cliente.sort_values(by="Data", inplace=True)

    # Foto do cliente
    link_foto = status_df.loc[status_df['Cliente'] == cliente_selecionado, 'LinkFoto']
    if not link_foto.empty and isinstance(link_foto.values[0], str):
        try:
            response = requests.get(link_foto.values[0])
            img = Image.open(BytesIO(response.content))
            st.image(img, caption=cliente_selecionado, width=200)
        except:
            st.warning("Erro ao carregar a imagem do cliente.")
    
    # Cálculos
    ultimo_atendimento = dados_cliente["Data"].max().date()
    hoje = datetime.today().date()
    dias_desde_ultimo = (hoje - ultimo_atendimento).days
    frequencia_media = dados_cliente["Data"].diff().dt.days.mean()
    intervalo_medio = frequencia_media
    mais_atendido_por = dados_cliente["Funcionario"].mode().iloc[0]
    ticket_medio = dados_cliente["Valor Total"].mean()

    # Status de atraso
    if dias_desde_ultimo <= frequencia_media * 1.2:
        status = "🟢 Em dia"
    elif dias_desde_ultimo <= frequencia_media * 1.5:
        status = "🟠 Pouco atrasado"
    else:
        status = "🔴 Muito atrasado"

    # VIP
    vip = status_df.loc[status_df['Cliente'] == cliente_selecionado, 'VIP']
    vip_status = "Sim ⭐" if not vip.empty and str(vip.values[0]).strip().lower() == "sim" else "Não"

    # Tempo total no salão
    if "Tempo Total (min)" in dados_cliente.columns:
        tempo_total = dados_cliente["Tempo Total (min)"].sum()
        tempo_total_formatado = formatar_tempo(tempo_total)
    else:
        tempo_total_formatado = "Indisponível"

    # Layout
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown("### 📅 Último Atendimento")
        st.subheader(f"{ultimo_atendimento.strftime('%d/%m/%Y')}")
    with col2:
        st.markdown("### 📊 Frequência Média")
        st.subheader(f"{frequencia_media:.1f} dias")
    with col3:
        st.markdown("### 🧭 Desde Último")
        st.subheader(f"{dias_desde_ultimo} dias")
    with col4:
        st.markdown("### 📌 Status")
        st.subheader(status)

    st.markdown("### 💡 Insights Adicionais")

    col5, col6, col7 = st.columns(3)
    with col5:
        st.markdown("🥇 **Cliente VIP**")
        st.subheader(vip_status)
    with col6:
        st.markdown("🧍‍♂️ **Mais atendido por**")
        st.subheader(mais_atendido_por)
    with col7:
        st.markdown("🕒 **Tempo Total no Salão**")
        st.subheader(tempo_total_formatado)

    col8, col9 = st.columns(2)
    with col8:
        st.markdown("🤑 **Ticket Médio**")
        st.subheader(f"R$ {ticket_medio:.2f}")
    with col9:
        st.markdown("📅 **Intervalo Médio**")
        st.subheader(f"{intervalo_medio:.1f} dias")
