# 1_Agendamentos.py
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time

st.set_page_config(page_title="Agendamentos", page_icon="📅", layout="wide")
st.title("📅 Agendamentos")

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "dados casulo"  # mesma aba do print

COLS_BASE = [
    "Paciente","Agendamento","Data","Hora inicio","Hora saida",
    "Terapeuta","Valor","Data de pagamento","Vencimento"
]

# ===== CONEXÃO =====
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

    # renomeia "Data de pag..." se vier truncado
    for c in df.columns:
        if c.lower().startswith("data de pag"):
            df = df.rename(columns={c: "Data de pagamento"})
            break

    for c in COLS_BASE:
        if c not in df.columns:
            df[c] = ""

    df = df[COLS_BASE].copy()
    df["__row__"] = (df.index + 2).astype(int)   # linha real na planilha (cabeçalho = 1)

    # conversões
    def to_date(x):
        s = str(x).strip()
        if not s or s.lower() == "none":
            return pd.NaT
        for fmt in ("%d/%m/%Y","%Y-%m-%d"):
            try:
                return pd.to_datetime(s, format=fmt).date()
            except:
                pass
        try:
            return pd.to_datetime(s, dayfirst=True).date()
        except:
            return pd.NaT

    def to_time(x):
        s = str(x).strip()
        for fmt in ("%H:%M:%S","%H:%M"):
            try:
                return datetime.strptime(s, fmt).time()
            except:
                pass
        return None

    def to_float(x):
        try:
            return float(str(x).replace(",", "."))
        except:
            return None

    df["Data"] = df["Data"].apply(to_date)
    df["Hora inicio"] = df["Hora inicio"].apply(to_time)
    df["Hora saida"] = df["Hora saida"].apply(to_time)
    df["Vencimento"] = df["Vencimento"].apply(to_date)
    df["Data de pagamento"] = df["Data de pagamento"].apply(to_date)
    df["Valor"] = df["Valor"].apply(to_float)
    return df

def update_cell(row_idx, col_name, value):
    wks = conectar().worksheet(ABA_BASE)
    header = wks.row_values(1)
    col_idx = header.index(col_name) + 1
    if isinstance(value, date):
        value = value.strftime("%d/%m/%Y")
    if isinstance(value, time):
        value = value.strftime("%H:%M")
    wks.update_cell(row_idx, col_idx, value)

def append_row(values_list):
    conectar().worksheet(ABA_BASE).append_row(values_list, value_input_option="USER_ENTERED")

def delete_row(row_idx):
    conectar().worksheet(ABA_BASE).delete_rows(row_idx)

# ========== DADOS E FILTROS ==========
df = carregar()

f1, f2, f3, f4 = st.columns([2,2,2,2])
with f1:
    filtro_paciente = st.text_input("🔎 Paciente (contém)")
with f2:
    dt_de = st.date_input("De (Data)", value=None)
with f3:
    dt_ate = st.date_input("Até (Data)", value=None)
with f4:
    apenas_futuros = st.checkbox("Apenas futuros", value=False)

visu = df.copy()
if filtro_paciente:
    visu = visu[visu["Paciente"].str.contains(filtro_paciente, case=False, na=False)]
if dt_de:
    visu = visu[visu["Data"] >= dt_de]
if dt_ate:
    visu = visu[visu["Data"] <= dt_ate]
if apenas_futuros:
    hoje = date.today()
    visu = visu[visu["Data"].fillna(hoje) >= hoje]

# ====== TABELA (com formatação e Status colorido) ======
st.subheader("Agenda")

def fmt_date(d):
    try:
        return d.strftime("%d/%m/%Y")
    except:
        return ""

def fmt_time(t):
    try:
        return t.strftime("%H:%M")
    except:
        return ""

hoje = date.today()
def calc_status(row):
    dp, ven = row.get("Data de pagamento"), row.get("Vencimento")
    if pd.notna(dp):
        return "Pago"
    if pd.isna(ven):
        return ""
    return "Em atraso" if ven < hoje else "Em dia"

visu_tbl = visu.copy()
visu_tbl["Status"] = visu_tbl.apply(calc_status, axis=1)

# formatação apenas para exibição
visu_tbl["Data"] = visu_tbl["Data"].apply(fmt_date)
visu_tbl["Hora inicio"] = visu_tbl["Hora inicio"].apply(fmt_time)
visu_tbl["Hora saida"]  = visu_tbl["Hora saida"].apply(fmt_time)
visu_tbl["Vencimento"]  = visu_tbl["Vencimento"].apply(fmt_date)

# colunas a exibir (sem "Data de pagamento")
mostrar = [
    "Paciente","Agendamento","Data","Hora inicio","Hora saida",
    "Terapeuta","Valor","Vencimento","Status"
]
visu_tbl = visu_tbl[mostrar].sort_values(by=["Data","Hora inicio"], na_position="last")

# função de estilo
def color_status(val):
    if val == "Pago":
        return "background-color: rgba(16, 185, 129, 0.2); color: #10b981; font-weight: 600"  # verde
    if val == "Em dia":
        return "background-color: rgba(59, 130, 246, 0.2); color: #3b82f6; font-weight: 600"  # azul
    if val == "Em atraso":
        return "background-color: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight: 700"  # vermelho
    return ""

styled = visu_tbl.style.apply(lambda s: [color_status(v) for v in s], subset=["Status"])

st.dataframe(styled, use_container_width=True)

st.markdown("---")
st.subheader("Adicionar / Editar agendamento")
modo = st.radio("Modo", ["Adicionar", "Editar", "Excluir"], horizontal=True)

# ========= seleção de linha para editar/excluir =========
if modo in ("Editar", "Excluir"):
    opcoes = visu if not visu.empty else df
    escolha = st.selectbox(
        "Selecione o registro",
        opcoes.apply(lambda r: f"Linha {r['__row__']}: {r['Paciente']} - {fmt_date(r['Data'])} {fmt_time(r['Hora inicio'])}", axis=1)
             .tolist()
    )
    row_sel = int(escolha.split()[1].strip(":"))
    registro = df[df["__row__"]==row_sel].iloc[0]
else:
    row_sel, registro = None, None

colA, colB = st.columns([3,2])
with colA:
    paciente   = st.text_input("Paciente", value=(registro["Paciente"] if registro is not None else ""))
    agenda_txt = st.text_input("Agendamento", value=(registro["Agendamento"] if registro is not None else ""))
    terapeuta  = st.text_input("Terapeuta", value=(registro["Terapeuta"] if registro is not None else ""))
with colB:
    data_ag    = st.date_input("Data", value=(registro["Data"] if (registro is not None and pd.notna(registro["Data"])) else None))
    hora_ini   = st.time_input("Hora início", value=(registro["Hora inicio"] if ( registro is not None and isinstance(registro["Hora inicio"], time)) else time(8,0)))
    hora_fim   = st.time_input("Hora saída",  value=(registro["Hora saida"]  if ( registro is not None and isinstance(registro["Hora saida"], time))  else time(9,0)))

btn1, btn2 = st.columns(2)

if modo == "Adicionar":
    if btn1.button("➕ Adicionar"):
        nova = [
            paciente.strip(), agenda_txt.strip(),
            data_ag.strftime("%d/%m/%Y") if data_ag else "",
            hora_ini.strftime("%H:%M") if hora_ini else "",
            hora_fim.strftime("%H:%M") if hora_fim else "",
            terapeuta.strip(),
            "",  # Valor (financeiro controlado na outra página)
            "",  # Data de pagamento (fica vazia aqui)
            ""   # Vencimento (se quiser, preencha na página de pagamentos)
        ]
        append_row(nova)
        st.success("Agendamento adicionado.")
        st.cache_data.clear()

elif modo == "Editar":
    if btn1.button("💾 Salvar alterações"):
        update_cell(row_sel, "Paciente", paciente.strip())
        update_cell(row_sel, "Agendamento", agenda_txt.strip())
        update_cell(row_sel, "Terapeuta", terapeuta.strip())
        update_cell(row_sel, "Data", data_ag if data_ag else "")
        update_cell(row_sel, "Hora inicio", hora_ini if hora_ini else "")
        update_cell(row_sel, "Hora saida", hora_fim if hora_fim else "")
        st.success(f"Linha {row_sel} atualizada.")
        st.cache_data.clear()

elif modo == "Excluir":
    if btn2.button("🗑️ Excluir registro"):
        delete_row(row_sel)
        st.success(f"Linha {row_sel} excluída.")
        st.cache_data.clear()
