# -*- coding: utf-8 -*-
# 9_Resultado_Financeiro_Pro.py — Resultado consolidado com análise profunda de DESPESAS
import streamlit as st
import pandas as pd
import numpy as np
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
import io
from datetime import datetime

st.set_page_config(layout="wide", page_title="📊 Resultado Financeiro Pro", page_icon="💈")
st.title("💈📊 Resultado Financeiro — Visão PRO (Receita x Despesas)")

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

# Palavras-chave para categorizar despesas (pode editar livremente)
CATEG_MAP = {
    "comissão": "Comissão",
    "taxa|maquin|stone|sumup|clip|cartão|cartao": "Taxa de Cartão",
    "luz|energia|enel|celg|equatorial": "Energia",
    "água|agua|saneago": "Água",
    "aluguel|aluguel sala|locação|locacao": "Aluguel",
    "produto|pomada|gel|cera|creme|lâmina|lamina|barber|tesoura|máquina|maquina": "Produtos/Insumos",
    "limpeza|detergente|sabão|sabao|álcool|alcool|descartável|descartavel": "Limpeza/EPI",
    "internet|wifi|roteador|modem|provedor|claro|vivo|oi|tim": "Internet/Telefonia",
    "marketing|instagram|facebook|canva|anúncio|anuncio|arte|impressão|impressao|banner": "Marketing",
    "manutenção|manutencao|reparo|conserto|técnico|tecnico|suporte": "Manutenção",
    "transporte|uber|combustível|combustivel|gasolina|estacionamento": "Transporte",
    "imposto|taxa prefeitura|alvará|alvara|mei|simples": "Impostos/Taxas",
    "equipamento|cadeira|espelho|móvel|movel|microfone|câmera|camera|pc|notebook": "Equipamentos",
}

# =========================
# CONEXÃO GOOGLE SHEETS
# =========================
@st.cache_resource(show_spinner=False)
def _connect():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

@st.cache_data(show_spinner=True)
def load_data():
    sh = _connect()
    df_base = get_as_dataframe(sh.worksheet("Base de Dados")).dropna(how="all")
    df_desp = get_as_dataframe(sh.worksheet("Despesas")).dropna(how="all")
    return df_base, df_desp

df_rec, df_desp = load_data()

# =========================
# LIMPEZA / TIPOS
# =========================
def to_num(x):
    if pd.isna(x): return 0.0
    s = str(x)
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except:
        return pd.to_numeric(s, errors="coerce") or 0.0

# RECEITAS
df_rec = df_rec.copy()
df_rec.columns = df_rec.columns.str.strip()
if "Data" in df_rec.columns:
    df_rec["Data"] = pd.to_datetime(df_rec["Data"], errors="coerce", dayfirst=True)
    df_rec = df_rec.dropna(subset=["Data"])
    df_rec["Ano"] = df_rec["Data"].dt.year
    df_rec["Mês"] = df_rec["Data"].dt.month
if "Valor" in df_rec.columns:
    df_rec["ValorNum"] = df_rec["Valor"].apply(to_num)
else:
    df_rec["ValorNum"] = 0.0

# DESPESAS
df_desp = df_desp.copy()
df_desp.columns = df_desp.columns.str.strip()
for col in ["Data", "Prestador", "Descrição", "Valor", "Me Pag", "RefID"]:
    if col not in df_desp.columns:
        df_desp[col] = np.nan

df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce", dayfirst=True)
df_desp = df_desp.dropna(subset=["Data"])
df_desp["Ano"] = df_desp["Data"].dt.year
df_desp["Mês"] = df_desp["Data"].dt.month
df_desp["ValorNum"] = df_desp["Valor"].apply(to_num)

# Tipo (segundo sua regra: Vinicius = Comissão; demais = Despesa do Salão)
df_desp["Tipo"] = np.where(df_desp["Prestador"].astype(str).str.contains("vinicius", case=False, na=False),
                           "Comissão (Vinicius)", "Despesa do Salão")

# Categoria por palavras-chave em Descrição (fallback = "Outros")
def classif_categoria(desc: str) -> str:
    text = str(desc).lower()
    for patt, nome in CATEG_MAP.items():
        if pd.notna(text) and len(text) and (pd.Series([text]).str.contains(patt, regex=True).iloc[0]):
            return nome
    return "Outros"

df_desp["Categoria"] = df_desp["Descrição"].apply(classif_categoria)

# =========================
# FILTROS
# =========================
anos = sorted(df_desp["Ano"].dropna().unique(), reverse=True)
c1, c2, c3, c4, c5 = st.columns([1,1,1,1,1])
ano_sel = c1.multiselect("🗓️ Ano", anos, default=anos[:1])
meses_pt = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
mes_sel = c2.multiselect("📅 Mês", list(meses_pt.keys()), format_func=lambda m: meses_pt[m])

prestadores = sorted(df_desp["Prestador"].dropna().unique())
prest_sel = c3.multiselect("👤 Prestador", prestadores)

cats = sorted(df_desp["Categoria"].dropna().unique())
cat_sel = c4.multiselect("🏷️ Categoria", cats)

formas = sorted(df_desp["Me Pag"].dropna().astype(str).unique())
forma_sel = c5.multiselect("💳 Forma de Pagamento", formas)

f = df_desp.copy()
if ano_sel:  f = f[f["Ano"].isin(ano_sel)]
if mes_sel:  f = f[f["Mês"].isin(mes_sel)]
if prest_sel: f = f[f["Prestador"].isin(prest_sel)]
if cat_sel:   f = f[f["Categoria"].isin(cat_sel)]
if forma_sel: f = f[f["Me Pag"].astype(str).isin(forma_sel)]

# RECEITA no mesmo recorte (por ano/mês)
fr = df_rec.copy()
if ano_sel: fr = fr[fr["Ano"].isin(ano_sel)]
if mes_sel: fr = fr[fr["Mês"].isin(mes_sel)]
receita_total = float(fr["ValorNum"].sum())

# =========================
# KPIs
# =========================
comissao = float(f.loc[f["Tipo"]=="Comissão (Vinicius)","ValorNum"].sum())
desp_salao = float(f.loc[f["Tipo"]=="Despesa do Salão","ValorNum"].sum())
desp_total = comissao + desp_salao
lucro = receita_total - desp_total
margem = (lucro/receita_total*100.0) if receita_total>0 else 0.0
pct_comissao = (comissao/receita_total*100.0) if receita_total>0 else 0.0

st.subheader("📌 Indicadores do período filtrado")
k1,k2,k3,k4,k5 = st.columns(5)
k1.metric("Receita", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v",".")) 
k2.metric("Comissões (Vinicius)", f"R$ {comissao:,.2f}".replace(",", "v").replace(".", ",").replace("v","."), f"{pct_comissao:.1f}% da receita")
k3.metric("Despesas do Salão", f"R$ {desp_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v","."))
k4.metric("Despesas Totais", f"R$ {desp_total:,.2f}".replace(",", "v").replace(".", ",").replace("v","."))
k5.metric("Lucro", f"R$ {lucro:,.2f}".replace(",", "v").replace(".", ",").replace("v","."), f"Margem {margem:.1f}%")

st.divider()

# =========================
# TABELAS — Top Prestadores / Categorias
# =========================
st.subheader("🏆 Top prestadores e categorias")

cA, cB = st.columns(2)
top_prest = (f.groupby("Prestador", as_index=False)["ValorNum"]
               .sum().sort_values("ValorNum", ascending=False))
top_prest["Gasto (R$)"] = top_prest["ValorNum"].map(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v","."))
cA.dataframe(top_prest[["Prestador","Gasto (R$)"]], use_container_width=True, height=400)

top_categ = (f.groupby("Categoria", as_index=False)["ValorNum"]
               .sum().sort_values("ValorNum", ascending=False))
top_categ["Gasto (R$)"] = top_categ["ValorNum"].map(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v","."))
cB.dataframe(top_categ[["Categoria","Gasto (R$)"]], use_container_width=True, height=400)

st.divider()

# =========================
# GRÁFICOS
# =========================
st.subheader("📈 Visualizações")

# Evolução mensal por TIPO
serie = (f.groupby(["Ano","Mês","Tipo"], as_index=False)["ValorNum"].sum())
if not serie.empty:
    serie["MesTxt"] = serie["Mês"].map(lambda m: f"{m:02d}")
    fig_line = px.line(serie.sort_values(["Ano","Mês"]),
                       x="MesTxt", y="ValorNum", color="Tipo",
                       markers=True, labels={"MesTxt":"Mês","ValorNum":"R$"},
                       title="Evolução mensal de despesas por Tipo")
    fig_line.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    st.plotly_chart(fig_line, use_container_width=True)

c1, c2 = st.columns(2)

# Barras — Top prestadores
if not top_prest.empty:
    fig_prest = px.bar(top_prest.head(15), x="Prestador", y="ValorNum",
                       text_auto=".2s", labels={"ValorNum":"R$"},
                       title="Top prestadores (gasto)")
    fig_prest.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    c1.plotly_chart(fig_prest, use_container_width=True)

# Pizza — Categorias
if not top_categ.empty:
    fig_cat = px.pie(top_categ, names="Categoria", values="ValorNum", title="Composição por categoria")
    fig_cat.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    c2.plotly_chart(fig_cat, use_container_width=True)

# Barras — Formas de pagamento
st.subheader("💳 Formas de pagamento (Despesas)")
formas_df = (f.assign(Meio=f["Me Pag"].astype(str))
               .groupby("Meio", as_index=False)["ValorNum"].sum()
               .sort_values("ValorNum", ascending=False))
if not formas_df.empty:
    fig_meios = px.bar(formas_df, x="Meio", y="ValorNum", text_auto=".2s",
                       labels={"ValorNum":"R$"}, title="Gasto por forma de pagamento")
    fig_meios.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    st.plotly_chart(fig_meios, use_container_width=True)

# Waterfall — Receita → Lucro
st.subheader("🏗️ Ponte Receita → Lucro (Waterfall)")
wf = go.Figure(go.Waterfall(
    name="Fluxo",
    orientation="v",
    measure=["relative","relative","relative","total"],
    x=["Receita","- Comissão Vinicius","- Despesa do Salão","Lucro"],
    textposition="outside",
    y=[receita_total, -comissao, -desp_salao, 0],
))
wf.update_layout(title="De Receita a Lucro", showlegend=False,
                 plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
st.plotly_chart(wf, use_container_width=True)

st.divider()

# =========================
# DETALHAMENTO (com RefID)
# =========================
st.subheader("📋 Detalhamento das despesas (linhas)")
det = f[["Data","Prestador","Descrição","Categoria","Tipo","Me Pag","ValorNum","RefID"]].sort_values("Data", ascending=False)
det["Valor (R$)"] = det["ValorNum"].map(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v","."))
det = det.drop(columns=["ValorNum"])
st.dataframe(det, use_container_width=True, height=420)

# =========================
# EXPORTAÇÃO
# =========================
st.subheader("📤 Exportar Excel")
# Abas:
# 1) KPIs  2) Top Prestadores  3) Categorias  4) Formas  5) Série Mensal  6) Detalhamento
serie_mensal = (f.groupby(["Ano","Mês","Tipo"], as_index=False)["ValorNum"].sum().sort_values(["Ano","Mês","Tipo"]))
export_kpis = pd.DataFrame({
    "Receita":[receita_total],
    "Comissão (Vinicius)":[comissao],
    "Despesa do Salão":[desp_salao],
    "Despesas Totais":[desp_total],
    "Lucro":[lucro],
    "Margem (%)":[margem],
    "Comissão/Receita (%)":[pct_comissao]
})

buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="xlsxwriter") as wr:
    export_kpis.to_excel(wr, index=False, sheet_name="KPIs")
    top_prest.to_excel(wr, index=False, sheet_name="Top Prestadores")
    top_categ.to_excel(wr, index=False, sheet_name="Categorias")
    formas_df.to_excel(wr, index=False, sheet_name="Formas Pagto")
    serie_mensal.to_excel(wr, index=False, sheet_name="Série Mensal")
    det.to_excel(wr, index=False, sheet_name="Detalhamento")
    wr.save()
    data_xlsx = buf.getvalue()

st.download_button(
    "⬇️ Baixar Excel Completo",
    data=data_xlsx,
    file_name=f"resultado_financeiro_pro_{datetime.now().date()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
