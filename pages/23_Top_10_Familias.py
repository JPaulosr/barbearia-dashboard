import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

# === Cliente Família - Top 10 Grupos com barra colorida ===
st.subheader("👨‍👩‍👧‍👦 Cliente Família — Top 10 Grupos")

# Junta dados com 'Família'
df_familia = df.merge(df_fotos[["Cliente", "Família"]], on="Cliente", how="left")
df_familia = df_familia[df_familia["Família"].notna() & (df_familia["Família"].str.strip() != "")]

# Remove duplicatas de atendimento (cliente + data)
df_familia = df_familia.drop_duplicates(subset=["Cliente", "Data"])

# Soma valor total gasto por todos os membros da família
familia_valores = df_familia.groupby("Família")["Valor"].sum().sort_values(ascending=False)

# Pega Top 10 por valor gasto
top_familias = familia_valores.head(10)
max_valor = top_familias.max()

# Cores padrão (alternadas) se passar do top 3
cores_top3 = ["#FFD700", "#C0C0C0", "#CD7F32"]
cor_default = "#FF914D"

for i, (familia, valor_total) in enumerate(top_familias.items()):
    membros = df_fotos[df_fotos["Família"] == familia]
    qtd_membros = len(membros)

    nome_pai = familia.replace("Família ", "").strip().lower()
    nome_pai_formatado = nome_pai.capitalize()
    membro_foto = None

    for idx, row in membros.iterrows():
        cliente_nome = str(row["Cliente"]).strip().lower()
        foto = row["Foto"]
        if cliente_nome == nome_pai and pd.notna(foto):
            membro_foto = foto
            break

    if not membro_foto and membros["Foto"].notna().any():
        membro_foto = membros["Foto"].dropna().values[0]

    linha = st.columns([0.05, 0.12, 0.83])
    pos_emoji = f"{i+1}º" if i > 2 else ["🥇", "🥈", "🥉"][i]
    linha[0].markdown(f"### {pos_emoji}")

    if membro_foto:
        try:
            response = requests.get(membro_foto)
            img = Image.open(BytesIO(response.content))
            linha[1].image(img, width=50)
        except:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)
    else:
        linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

    # Texto e barra de progresso
    texto = f"Família **{nome_pai_formatado}** — R$ {valor_total:.2f} | {qtd_membros} membros"
    progresso_pct = int((valor_total / max_valor) * 100)
    cor_barra = cores_top3[i] if i < 3 else cor_default

    linha[2].markdown(texto)
    barra_html = f"""
    <div style="background-color:#333;border-radius:10px;height:14px;width:100%;margin-top:4px;margin-bottom:4px;">
      <div style="background-color:{cor_barra};width:{progresso_pct}%;height:100%;border-radius:10px;"></div>
    </div>
    <small style="color:gray;">{progresso_pct}% do líder</small>
    """
    linha[2].markdown(barra_html, unsafe_allow_html=True)
