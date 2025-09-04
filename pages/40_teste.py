# -*- coding: utf-8 -*-
# 9_Resultado_Financeiro_Pro.py — Receita correta (regras configuráveis) + Despesas

import streamlit as st
import pandas as pd
import numpy as np
import gspread, re, io
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

st.set_page_config(layout="wide", page_title="📊 Resultado Financeiro Pro", page_icon="💈")
st.title("💈📊 Resultado Financeiro — Visão PRO (Receita x Despesas)")

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
CACHE_VERSION = 3  # mude p/ invalidar cache
MESES_PT = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}

# Palavras que indicam NÃO receita na Base de Dados (linhas que vamos excluir)
PADROES_NAO_RECEITA = [
    "despesa", "estorno", "ajuste", "transfer", "saida", "pagar? fiado", "fiado pagamento",
    "pagamento fiado", "baixa fiado", "cofre saida"
]

CATEG_MAP = {
    "comissão": "Comissão",
    "taxa|maquin|stone|sumup|clip|cartão|cartao": "Taxa de Cartão",
    "luz|energia|enel|celg|equatorial": "Energia",
    "água|agua|saneago": "Água",
    "aluguel|locação|locacao": "Aluguel",
    "produto|pomada|gel|cera|creme|lâmina|lamina|barber|tesoura|máquina|maquina": "Produtos/Insumos",
    "limpeza|detergente|sabão|sabao|álcool|alcool|descartável|descartavel": "Limpeza/EPI",
    "internet|wifi|roteador|modem|provedor|claro|vivo|oi|tim": "Internet/Telefonia",
    "marketing|instagram|facebook|canva|anúncio|anuncio|arte|impressão|impressao|banner": "Marketing",
    "manutenção|manutencao|reparo|conserto|técnico|tecnico|suporte": "Manutenção",
    "transporte|uber|combustível|combustivel|gasolina|estacionamento": "Transporte",
    "imposto|taxa prefeitura|alvará|alvara|mei|simples": "Impostos/Taxas",
    "equipamento|cadeira|espelho|móvel|movel|microfone|câmera|camera|pc|notebook": "Equipamentos",
}

def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def to_brl(x) -> float:
    if pd.isna(x): return 0.0
    s = str(x).strip()
    if not s: return 0.0
    s = (s.replace('R$', '').replace(' ', '')
           .replace('\u00A0','').replace('−','-'))
    s = re.sub(r'[^0-9,.\-]', '', s)

    if s.count(',') == 1 and s.count('.') >= 1:      # 1.234,56
        s = s.replace('.', '').replace(',', '.')
    elif s.count(',') == 1:                          # 1234,56
        s = s.replace(',', '.')
    elif s.count('.') == 1 and s.count(',') == 0:    # 73.27  ou 45.724
        frac = s.split('.')[-1]
        if len(frac) == 3: s = s.replace('.', '')    # milhar
    else:
        s = s.replace('.', '')
    try:
        return float(s)
    except:
        return 0.0

def classif_categoria(desc: str) -> str:
    text = str(desc).lower()
    for patt, nome in CATEG_MAP.items():
        if pd.Series([text]).str.contains(patt, regex=True).iloc[0]:
            return nome
    return "Outros"

# =========================
# CONEXÃO
# =========================
@st.cache_resource(show_spinner=False)
def _connect():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

@st.cache_data(show_spinner=True)
def load_data(_v: int):
    sh = _connect()
    df_base = get_as_dataframe(sh.worksheet("Base de Dados")).dropna(how="all")
    df_desp = get_as_dataframe(sh.worksheet("Despesas")).dropna(how="all")
    return df_base, df_desp

# botão para limpar cache
left, _ = st.columns([1,6])
if left.button("♻️ Forçar recarga (limpar cache)"):
    st.cache_data.clear(); st.cache_resource.clear(); st.experimental_rerun()

df_rec_raw, df_desp_raw = load_data(CACHE_VERSION)

# =========================
# LIMPEZA
# =========================
# Receitas
df_rec = df_rec_raw.copy()
df_rec.columns = df_rec.columns.str.strip()
df_rec["Data"] = pd.to_datetime(df_rec["Data"], errors="coerce", dayfirst=True)
df_rec = df_rec.dropna(subset=["Data"])
df_rec["Ano"] = df_rec["Data"].dt.year
df_rec["Mês"] = df_rec["Data"].dt.month
df_rec["ValorNum"] = df_rec.get("Valor", 0).apply(to_brl)
if "ValorBruto" in df_rec.columns:
    df_rec["ValorBrutoNum"] = df_rec["ValorBruto"].apply(to_brl)
else:
    df_rec["ValorBrutoNum"] = np.nan
if "TaxaCartaoValor" in df_rec.columns:
    df_rec["TaxaCartaoValorNum"] = df_rec["TaxaCartaoValor"].apply(to_brl)
else:
    df_rec["TaxaCartaoValorNum"] = 0.0

# Despesas
df_desp = df_desp_raw.copy()
df_desp.columns = df_desp.columns.str.strip()
for col in ["Data","Prestador","Descrição","Valor","Me Pag","RefID"]:
    if col not in df_desp.columns: df_desp[col] = np.nan
df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce", dayfirst=True)
df_desp = df_desp.dropna(subset=["Data"])
df_desp["Ano"] = df_desp["Data"].dt.year
df_desp["Mês"] = df_desp["Data"].dt.month
df_desp["ValorNum"] = df_desp["Valor"].apply(to_brl)
df_desp["Tipo"] = np.where(df_desp["Prestador"].astype(str).str.contains("vinici", case=False, na=False),
                           "Comissão (Vinicius)", "Despesa do Salão")
df_desp["Categoria"] = df_desp["Descrição"].apply(classif_categoria)

# =========================
# FILTROS (topo)
# =========================
anos = sorted(df_desp["Ano"].dropna().unique(), reverse=True)
cA,cB,cC,cD,cE = st.columns([1,1,1,1,1])
ano_sel = cA.multiselect("🗓️ Ano", anos, default=anos[:1])
mes_sel = cB.multiselect("📅 Mês", list(MESES_PT.keys()), format_func=lambda m: MESES_PT[m])
prest_sel = cC.multiselect("👤 Prestador", sorted(df_desp["Prestador"].dropna().unique()))
cat_sel = cD.multiselect("🏷️ Categoria", sorted(df_desp["Categoria"].dropna().unique()))
forma_sel = cE.multiselect("💳 Forma de Pagamento", sorted(df_desp["Me Pag"].dropna().astype(str).unique()))

# Subconjuntos de despesas conforme filtros
f = df_desp.copy()
if ano_sel:  f = f[f["Ano"].isin(ano_sel)]
if mes_sel:  f = f[f["Mês"].isin(mes_sel)]
if prest_sel: f = f[f["Prestador"].isin(prest_sel)]
if cat_sel:   f = f[f["Categoria"].isin(cat_sel)]
if forma_sel: f = f[f["Me Pag"].astype(str).isin(forma_sel)]
f = f[f["ValorNum"] > 0]  # evita sinais trocados

# =========================
# RECEITA — regras configuráveis
# =========================
st.markdown("#### ⚙️ Regra da Receita")
colR1, colR2 = st.columns([1,1])
regra = colR1.radio(
    "Como somar receita?",
    ["Líquido (Valor)", "Bruto - Taxa (se existir)"],
    horizontal=True,
    help="Escolha se a receita base é o Valor líquido registrado na Base de Dados ou o Valor Bruto menos a Taxa do cartão."
)
somar_cx = colR2.toggle("➕ Somar caixinha/gorjeta", value=True)

fr = df_rec.copy()
if ano_sel: fr = fr[fr["Ano"].isin(ano_sel)]
if mes_sel: fr = fr[fr["Mês"].isin(mes_sel)]

# Remove linhas que NÃO são receita (pela coluna Tipo, se existir)
if "Tipo" in fr.columns:
    mask_bad = fr["Tipo"].astype(str).str.lower().apply(
        lambda t: any(k in t for k in PADROES_NAO_RECEITA)
    )
    fr = fr[~mask_bad]

# Garante valores válidos
fr = fr[fr["ValorNum"].astype(float) >= 0]

# Base da receita
if regra.startswith("Bruto"):
    base_receita = fr["ValorBrutoNum"].fillna(fr["ValorNum"]) - fr["TaxaCartaoValorNum"].fillna(0.0)
else:
    base_receita = fr["ValorNum"]

# Extras (caixinha/gorjeta)
extras_cols = [c for c in ["Caixinha","CaixinhaDia","CaixinhaDiaTotal","Gorjeta","Caixinha_Fundo","CaixinhaFundo"] if c in fr.columns]
extras_total = 0.0
if somar_cx and extras_cols:
    for c in extras_cols:
        fr[c] = fr[c].apply(to_brl)
    extras_total = fr[extras_cols].sum(axis=1).sum()

receita_total = float(base_receita.sum() + extras_total)

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
k1.metric("Receita", brl(receita_total))
k2.metric("Comissões (Vinicius)", brl(comissao), f"{pct_comissao:.1f}% da receita")
k3.metric("Despesas do Salão", brl(desp_salao))
k4.metric("Despesas Totais", brl(desp_total))
k5.metric("Lucro", brl(lucro), f"Margem {margem:.1f}%")

with st.expander("🔎 Conferência da receita"):
    base_nome = "Valor (líquido)" if regra.startswith("Líquido") else "ValorBruto - Taxa"
    st.write(f"Base usada: **{base_nome}**")
    st.write("Soma base:", brl(float(base_receita.sum())))
    st.write("Extras (caixinha/gorjeta):", brl(float(extras_total)))
    if "Tipo" in df_rec.columns:
        removidas = df_rec.loc[df_rec["Tipo"].astype(str).str.lower().apply(lambda t: any(k in t for k in PADROES_NAO_RECEITA))]
        st.caption(f"Linhas removidas por não serem receita: {len(removidas)}")

st.divider()

# =========================
# TABELAS — Top prestadores / categorias
# =========================
st.subheader("🏆 Top prestadores e categorias")
cA, cB = st.columns(2)

top_prest = (f.groupby("Prestador", as_index=False)["ValorNum"]
               .sum().sort_values("ValorNum", ascending=False))
top_prest["Gasto (R$)"] = top_prest["ValorNum"].map(brl)
cA.dataframe(top_prest[["Prestador","Gasto (R$)"]], use_container_width=True, height=380)

top_categ = (f.groupby("Categoria", as_index=False)["ValorNum"]
               .sum().sort_values("ValorNum", ascending=False))
top_categ["Gasto (R$)"] = top_categ["ValorNum"].map(brl)
cB.dataframe(top_categ[["Categoria","Gasto (R$)"]], use_container_width=True, height=380)

st.divider()

# =========================
# GRÁFICOS
# =========================
st.subheader("📈 Visualizações")
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
if not top_prest.empty:
    fig_prest = px.bar(top_prest.head(15), x="Prestador", y="ValorNum",
                       text_auto=".2s", labels={"ValorNum":"R$"},
                       title="Top prestadores (gasto)")
    fig_prest.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    c1.plotly_chart(fig_prest, use_container_width=True)
if not top_categ.empty:
    fig_cat = px.pie(top_categ, names="Categoria", values="ValorNum", title="Composição por categoria")
    fig_cat.update_layout(paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    c2.plotly_chart(fig_cat, use_container_width=True)

st.subheader("💳 Formas de pagamento (Despesas)")
formas_df = (f.assign(Meio=f["Me Pag"].astype(str))
               .groupby("Meio", as_index=False)["ValorNum"].sum()
               .sort_values("ValorNum", ascending=False))
if not formas_df.empty:
    fig_meios = px.bar(formas_df, x="Meio", y="ValorNum", text_auto=".2s",
                       labels={"ValorNum":"R$"}, title="Gasto por forma de pagamento")
    fig_meios.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"), title_x=0.5)
    st.plotly_chart(fig_meios, use_container_width=True)

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
# DETALHAMENTO
# =========================
st.subheader("📋 Detalhamento das despesas (linhas)")
det = f[["Data","Prestador","Descrição","Categoria","Tipo","Me Pag","ValorNum","RefID"]].sort_values("Data", ascending=False)
det["Valor (R$)"] = det["ValorNum"].map(brl)
det = det.drop(columns=["ValorNum"])
st.dataframe(det, use_container_width=True, height=420)

# =========================
# EXPORTAÇÃO
# =========================
st.subheader("📤 Exportar Excel")
serie_mensal = (f.groupby(["Ano","Mês","Tipo"], as_index=False)["ValorNum"]
                  .sum().sort_values(["Ano","Mês","Tipo"]))
export_kpis = pd.DataFrame({
    "Receita":[receita_total],
    "Comissão (Vinicius)":[comissao],
    "Despesa do Salão":[desp_salao],
    "Despesas Totais":[desp_total],
    "Lucro":[lucro],
    "Margem (%)":[margem],
    "Comissão/Receita (%)":[(comissao/receita_total*100) if receita_total>0 else 0]
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
