import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import date

st.set_page_config(page_title="Pagamentos", page_icon="💳", layout="wide")
st.title("💳 Pagamentos")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_FIN = "Financeiro casulo"  # nova aba financeira

COLS_FIN = ["Paciente","Valor","Data de pagamento","Vencimento"]

@st.cache_resource
def conectar():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

@st.cache_data(ttl=60)
def carregar_fin():
    wks = conectar().worksheet(ABA_FIN)
    df = get_as_dataframe(wks, evaluate_formulas=True, header=0, dtype=str).dropna(how="all")

    # ajusta cabeçalho truncado "Data de pagame" -> "Data de pagamento"
    for c in df.columns:
        if c.lower().startswith("data de pag"):
            df = df.rename(columns={c: "Data de pagamento"})
            break

    for c in COLS_FIN:
        if c not in df.columns: df[c] = ""
    df = df[COLS_FIN].copy()
    df["__row__"] = (df.index + 2).astype(int)

    def to_date(x):
        s = str(x).strip()
        if not s: return pd.NaT
        for fmt in ("%d/%m/%Y","%Y-%m-%d"):
            try: return pd.to_datetime(s, format=fmt).date()
            except: pass
        try: return pd.to_datetime(s, dayfirst=True).date()
        except: return pd.NaT

    def to_float(x):
        try: return float(str(x).replace(",", "."))
        except: return None

    df["Vencimento"] = df["Vencimento"].apply(to_date)
    df["Data de pagamento"] = df["Data de pagamento"].apply(to_date)
    df["Valor"] = df["Valor"].apply(to_float)

    # Status
    hoje = date.today()
    def status(row):
        if pd.notna(row["Data de pagamento"]): return "Pago"
        if pd.isna(row["Vencimento"]): return ""
        return "Em atraso" if row["Vencimento"] < hoje else "Em dia"
    df["Status"] = df.apply(status, axis=1)
    return df

def update_cell(row_idx, col_name, value):
    wks = conectar().worksheet(ABA_FIN)
    header = wks.row_values(1)
    col_idx = header.index(col_name) + 1
    if isinstance(value, date): value = value.strftime("%d/%m/%Y")
    wks.update_cell(row_idx, col_idx, value)

def append_row(values_list):
    conectar().worksheet(ABA_FIN).append_row(values_list, value_input_option="USER_ENTERED")

def delete_row(row_idx):
    conectar().worksheet(ABA_FIN).delete_rows(row_idx)

# ======== DADOS / FILTROS ========
df = carregar_fin()

c1, c2, c3, c4 = st.columns([2,2,2,2])
with c1:
    paciente_f = st.text_input("🔎 Paciente (contém)")
with c2:
    status_f = st.selectbox("Status", ["Todos","Pago","Em dia","Em atraso"])
with c3:
    ven_de = st.date_input("Vencimento de", value=None)
with c4:
    ven_ate = st.date_input("Vencimento até", value=None)

visu = df.copy()
if paciente_f:
    visu = visu[visu["Paciente"].str.contains(paciente_f, case=False, na=False)]
if status_f != "Todos":
    visu = visu[visu["Status"] == status_f]
if ven_de:
    visu = visu[visu["Vencimento"] >= ven_de]
if ven_ate:
    visu = visu[visu["Vencimento"] <= ven_ate]

# ===== TABELA FORMATADA + CORES =====
st.subheader("Cobranças")

def fmt_date(d): return d.strftime("%d/%m/%Y") if isinstance(d, date) else ""

tbl = visu.copy()
tbl["Vencimento"] = tbl["Vencimento"].apply(fmt_date)
tbl["Data de pagamento"] = tbl["Data de pagamento"].apply(fmt_date)

def color_status(val):
    if val == "Pago":
        return "background-color: rgba(16,185,129,0.2); color:#10b981; font-weight:600"
    if val == "Em dia":
        return "background-color: rgba(59,130,246,0.2); color:#3b82f6; font-weight:600"
    if val == "Em atraso":
        return "background-color: rgba(239,68,68,0.2); color:#ef4444; font-weight:700"
    return ""

styled = tbl[["Paciente","Valor","Vencimento","Data de pagamento","Status","__row__"]] \
           .rename(columns={"__row__":"Linha"}) \
           .sort_values(by=["Status","Vencimento"], na_position="last") \
           .style.apply(lambda s: [color_status(v) for v in s], subset=["Status"])

st.dataframe(styled, use_container_width=True)

st.markdown("---")
st.subheader("Criar cobrança")
colA, colB, colC = st.columns([3,2,2])
with colA:
    paciente = st.text_input("Paciente")
with colB:
    valor = st.number_input("Valor", min_value=0.0, step=10.0)
with colC:
    venc = st.date_input("Vencimento", value=None)
if st.button("➕ Adicionar cobrança"):
    nova = [
        paciente.strip(),
        (str(valor).replace(".", ",")),
        "",  # Data de pagamento vazia
        venc.strftime("%d/%m/%Y") if venc else ""
    ]
    append_row(nova)
    st.success("Cobrança criada.")
    st.cache_data.clear()

st.markdown("---")
st.subheader("Marcar como pago / Editar / Excluir")
col1, col2 = st.columns([2,2])
with col1:
    if not df.empty:
        escolha = st.selectbox(
            "Selecione (linha – paciente – vencimento – valor)",
            df.apply(lambda r: f"{r['__row__']} – {r['Paciente']} – {fmt_date(r['Vencimento'])} – R${r['Valor'] or 0:.2f}", axis=1)
        )
        row_sel = int(escolha.split("–")[0].strip())
    else:
        st.info("Sem registros.")
        row_sel = None

with col2:
    acao = st.radio("Ação", ["Marcar pago","Editar vencimento/valor","Excluir"], horizontal=True)

if row_sel:
    if acao == "Marcar pago":
        data_pag = st.date_input("Data de pagamento", value=date.today())
        if st.button("✅ Confirmar pagamento"):
            update_cell(row_sel, "Data de pagamento", data_pag)
            st.success("Pagamento registrado.")
            st.cache_data.clear()

    elif acao == "Editar vencimento/valor":
        novo_venc = st.date_input("Novo vencimento", value=None, key="nv")
        novo_valor = st.number_input("Novo valor", min_value=0.0, step=10.0, key="vl")
        b1, b2 = st.columns(2)
        if b1.button("💾 Salvar edição"):
            if novo_venc: update_cell(row_sel, "Vencimento", novo_venc)
            update_cell(row_sel, "Valor", str(novo_valor).replace(".", ","))
            st.success("Atualizado.")
            st.cache_data.clear()
        if b2.button("🧹 Limpar pagamento"):
            update_cell(row_sel, "Data de pagamento", "")
            st.success("Pagamento removido.")
            st.cache_data.clear()

    elif acao == "Excluir":
        if st.button("🗑️ Excluir cobrança"):
            delete_row(row_sel)
            st.success("Registro excluído.")
            st.cache_data.clear()
