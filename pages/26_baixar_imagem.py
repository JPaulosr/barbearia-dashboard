import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, date

st.set_page_config(page_title="Pagamentos", page_icon="💳", layout="wide")
st.title("💳 Pagamentos")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "dados casulo"

COLS_BASE = [
    "Paciente","Agendamento","Data","Hora inicio","Hora saida",
    "Terapeuta","Valor","Data de pagamento","Vencimento"
]

@st.cache_resource
def conectar():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

@st.cache_data(ttl=60)
def carregar():
    wks = conectar().worksheet(ABA_BASE)
    df = get_as_dataframe(wks, evaluate_formulas=True, header=0, dtype=str).dropna(how="all")
    # renomeia "Data de pagame..." se vier cortado
    for c in df.columns:
        if c.lower().startswith("data de pag"):
            df = df.rename(columns={c: "Data de pagamento"})
            break
    for c in COLS_BASE:
        if c not in df.columns: df[c] = ""
    df = df[COLS_BASE].copy()
    df["__row__"] = (df.index + 2).astype(int)

    def to_date(x):
        for fmt in ("%d/%m/%Y","%Y-%m-%d"):
            try: return pd.to_datetime(x, format=fmt).date()
            except: pass
        try: return pd.to_datetime(x, dayfirst=True).date()
        except: return pd.NaT
    def to_float(x):
        try: return float(str(x).replace(",", "."))
        except: return None

    df["Data"] = df["Data"].apply(to_date)
    df["Vencimento"] = df["Vencimento"].apply(to_date)
    df["Data de pagamento"] = df["Data de pagamento"].apply(to_date)
    df["Valor"] = df["Valor"].apply(to_float)

    # Status calculado on-the-fly
    def status(row):
        if pd.notna(row["Data de pagamento"]): return "Pago"
        if pd.isna(row["Vencimento"]): return ""
        return "Em atraso" if row["Vencimento"] < date.today() else "Em dia"
    df["Status"] = df.apply(status, axis=1)
    return df

def update_cell(row_idx, col_name, val):
    wks = conectar().worksheet(ABA_BASE)
    header = wks.row_values(1)
    col_idx = header.index(col_name) + 1
    if isinstance(val, date):
        val = val.strftime("%d/%m/%Y")
    wks.update_cell(row_idx, col_idx, val)

df = carregar()

# ===== FILTROS =====
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

st.subheader("Cobranças")
st.dataframe(
    visu[["Paciente","Data","Valor","Vencimento","Data de pagamento","Status","__row__"]]
      .sort_values(["Status","Vencimento"], na_position="last")
      .rename(columns={"__row__":"Linha"}),
    use_container_width=True
)

st.markdown("---")
st.subheader("Adicionar/Atualizar pagamento")

modo = st.radio("Modo", ["Criar cobrança", "Marcar como pago", "Editar vencimento/valor"], horizontal=True)

if modo == "Criar cobrança":
    colA, colB, colC = st.columns([3,2,2])
    with colA:
        paciente = st.text_input("Paciente")
    with colB:
        valor = st.number_input("Valor", min_value=0.0, step=10.0)
    with colC:
        venc = st.date_input("Vencimento", value=None)
    if st.button("➕ Adicionar cobrança"):
        # Acrescenta nova linha na mesma aba mantendo campos de agenda vazios se necessário
        nova = [
            paciente.strip(), "", "", "", "",
            "", f"{valor}".replace(".", ","), "", venc.strftime("%d/%m/%Y") if venc else ""
        ]
        conectar().worksheet(ABA_BASE).append_row(nova, value_input_option="USER_ENTERED")
        st.success("Cobrança criada.")
        st.cache_data.clear()

elif modo == "Marcar como pago":
    em_aberto = df[df["Status"]!="Pago"]
    if em_aberto.empty:
        st.info("Nenhuma cobrança em aberto.")
    else:
        escolha = st.selectbox(
            "Selecione (linha – paciente – vencimento – valor)",
            em_aberto.apply(lambda r: f"{r['__row__']} – {r['Paciente']} – {r['Vencimento']} – R${r['Valor'] or 0:.2f}", axis=1)
        )
        row_sel = int(escolha.split("–")[0].strip())
        data_pag = st.date_input("Data de pagamento", value=date.today())
        if st.button("✅ Confirmar pagamento"):
            update_cell(row_sel, "Data de pagamento", data_pag)
            st.success(f"Linha {row_sel} marcada como paga.")
            st.cache_data.clear()

elif modo == "Editar vencimento/valor":
    escolha = st.selectbox(
        "Selecione a linha",
        df.apply(lambda r: f"{r['__row__']} – {r['Paciente']} – {r['Vencimento']} – R${r['Valor'] or 0:.2f}", axis=1)
    )
    row_sel = int(escolha.split("–")[0].strip())
    novo_venc = st.date_input("Novo vencimento", value=None)
    novo_valor = st.number_input("Novo valor", min_value=0.0, step=10.0)
    b1, b2 = st.columns(2)
    if b1.button("💾 Salvar"):
        if novo_venc: update_cell(row_sel, "Vencimento", novo_venc)
        update_cell(row_sel, "Valor", str(novo_valor).replace(".", ","))
        st.success(f"Linha {row_sel} atualizada.")
        st.cache_data.clear()
    if b2.button("🧹 Limpar pagamento (desfazer)"):
        update_cell(row_sel, "Data de pagamento", "")
        st.success(f"Linha {row_sel} sem data de pagamento.")
        st.cache_data.clear()
