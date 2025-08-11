# 12_Fiado.py — Fiado integrado à Base de Dados
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import date, datetime
from io import BytesIO
import pytz

st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide")
st.title("💳 Controle de Fiado (integrado à Base de Dados)")

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"
ABA_LANC = "Fiado_Lancamentos"
ABA_PAGT = "Fiado_Pagamentos"
TZ = pytz.timezone("America/Sao_Paulo")

# Campos que existem hoje na sua Base de Dados (ajuste se usar outros)
BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
# Colunas novas para fiado
EXTRA_COLS = ["StatusFiado","IDLancFiado","VencimentoFiado"]

# === Conexão ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def garantir_aba(ss, nome, cols):
    try:
        ws = ss.worksheet(nome)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=nome, rows=200, cols=max(10, len(cols)))
        ws.append_row(cols)
        return ws
    # garante cabeçalho mínimo
    header = ws.row_values(1)
    if not header:
        ws.append_row(cols)
    return ws

def garantir_colunas_base(ss):
    ws = garantir_aba(ss, ABA_BASE, BASE_COLS_MIN + EXTRA_COLS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    # garante existência das colunas mínimas e extras
    for c in BASE_COLS_MIN + EXTRA_COLS:
        if c not in df.columns:
            df[c] = None
    # reordena para padronizar
    df = df[[*BASE_COLS_MIN, *EXTRA_COLS, *[c for c in df.columns if c not in BASE_COLS_MIN+EXTRA_COLS]]]
    ws.clear()
    set_with_dataframe(ws, df)
    return ws

@st.cache_data
def carregar_tudo():
    ss = conectar_sheets()
    # garantir abas
    ws_base = garantir_colunas_base(ss)
    ws_lanc = garantir_aba(ss, ABA_LANC, ["Data","Cliente","Descricao","Valor","Vencimento","Funcionario","Tipo","Servico","Combo","IDLanc"])
    ws_pagt = garantir_aba(ss, ABA_PAGT, ["Data","Cliente","Valor","FormaPagamento","IDLanc","Obs","IDPagamento"])

    df_base = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
    df_lanc = get_as_dataframe(ws_lanc, evaluate_formulas=True, header=0).dropna(how="all")
    df_pagt = get_as_dataframe(ws_pagt, evaluate_formulas=True, header=0).dropna(how="all")

    # normalizações
    if "Data" in df_base.columns:
        df_base["Data"] = pd.to_datetime(df_base["Data"], errors="coerce").dt.date
    if "Valor" in df_base.columns:
        df_base["Valor"] = pd.to_numeric(df_base["Valor"], errors="coerce")
    for c in ["Data","Vencimento"]:
        if c in df_lanc.columns:
            df_lanc[c] = pd.to_datetime(df_lanc[c], errors="coerce").dt.date
    if "Valor" in df_lanc.columns:
        df_lanc["Valor"] = pd.to_numeric(df_lanc["Valor"], errors="coerce")
    if "Data" in df_pagt.columns:
        df_pagt["Data"] = pd.to_datetime(df_pagt["Data"], errors="coerce").dt.date
    if "Valor" in df_pagt.columns:
        df_pagt["Valor"] = pd.to_numeric(df_pagt["Valor"], errors="coerce")

    # lista de clientes (Base + Lanc + status)
    clientes = set(df_base.get("Cliente", pd.Series(dtype=str)).dropna().astype(str).str.strip())
    try:
        df_status = get_as_dataframe(ss.worksheet(ABA_STATUS), evaluate_formulas=True, header=0).dropna(how="all")
        if "Cliente" in df_status.columns:
            clientes |= set(df_status["Cliente"].dropna().astype(str).str.strip())
    except gspread.WorksheetNotFound:
        pass
    if "Cliente" in df_lanc.columns:
        clientes |= set(df_lanc["Cliente"].dropna().astype(str).str.strip())
    clientes = sorted([c for c in clientes if c])

    return df_base, df_lanc, df_pagt, clientes

def salvar_df(nome_aba, df):
    ss = conectar_sheets()
    ws = ss.worksheet(nome_aba)
    ws.clear()
    set_with_dataframe(ws, df)

def append_row(nome_aba, vals):
    ss = conectar_sheets()
    ss.worksheet(nome_aba).append_row(vals, value_input_option="USER_ENTERED")

def gerar_id(prefixo):
    return f"{prefixo}-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}"

# === Cálculos de saldo por cliente (baseado em fiados em aberto) ===
def saldo_em_aberto_por_cliente(df_base, cliente):
    if df_base.empty: return 0.0
    df = df_base[(df_base["Cliente"]==cliente) & (df_base["StatusFiado"]=="Em aberto")]
    return float(df["Valor"].sum()) if "Valor" in df.columns else 0.0

# === UI ===
df_base, df_lanc, df_pagt, clientes = carregar_tudo()

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha:", ["➕ Lançar fiado","💰 Registrar pagamento","📋 Em aberto & exportação"])

# =============== Lançar fiado ===============
if acao == "➕ Lançar fiado":
    st.subheader("➕ Lançar fiado (gera linha na Base de Dados com StatusFiado='Em aberto')")
    c1, c2 = st.columns(2)
    with c1:
        cli = st.selectbox("Cliente", options=[""]+clientes, index=0, help="Digite para buscar; pode digitar um nome novo.")
        if not cli:
            cli = st.text_input("Ou digite o nome do cliente", "")
        serv = st.text_input("Serviço", value="Corte")
        tipo = st.selectbox("Tipo", ["Serviço","Produto"], index=0)
        combo = st.text_input("Combo (opcional)", value="")
        valor = st.number_input("Valor (R$)", min_value=0.0, step=5.0, format="%.2f")
    with c2:
        data_atend = st.date_input("Data do atendimento", value=date.today())
        venc = st.date_input("Vencimento (opcional)", value=date.today())
        func = st.text_input("Funcionário", value="JPaulo")
        fase = st.text_input("Fase", value="Dono + funcionário")
        periodo = st.selectbox("Período (opcional)", ["", "Manhã","Tarde","Noite"], index=0)

    if st.button("Salvar fiado", use_container_width=True):
        if not cli or valor <= 0:
            st.error("Informe cliente e valor.")
        else:
            idl = gerar_id("L")
            # 1) controle
            append_row(ABA_LANC, [
                data_atend.strftime("%Y-%m-%d"), cli, serv, valor,
                venc.strftime("%Y-%m-%d") if venc else "", func, tipo, serv, combo, idl
            ])
            # 2) linha na Base de Dados (não entra em receita)
            # garantir colunas
            ss = conectar_sheets()
            ws_base = garantir_colunas_base(ss)
            dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
            # cria registro
            nova = {
                "Data": data_atend.strftime("%Y-%m-%d"),
                "Serviço": serv,
                "Valor": valor,
                "Conta": "Fiado",
                "Cliente": cli,
                "Combo": combo,
                "Funcionário": func,
                "Fase": fase,
                "Tipo": tipo,
                "Período": periodo if periodo else "",
                "StatusFiado": "Em aberto",
                "IDLancFiado": idl,
                "VencimentoFiado": venc.strftime("%Y-%m-%d") if venc else ""
            }
            # garante colunas e anexa
            for c in BASE_COLS_MIN + EXTRA_COLS:
                if c not in dfb.columns: dfb[c] = None
            dfb = pd.concat([dfb, pd.DataFrame([nova])], ignore_index=True)
            salvar_df(ABA_BASE, dfb)
            st.success(f"Fiado salvo para **{cli}** — ID: {idl}")
            st.cache_data.clear()

# =============== Registrar pagamento ===============
elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento (marca fiado como Pago e cria linha normal na Base)")
    c1, c2 = st.columns(2)
    with c1:
        cli = st.selectbox("Cliente", options=clientes)
        hoje = date.today()
        data_pag = st.date_input("Data do pagamento", value=hoje)
        forma = st.selectbox("Forma de pagamento", ["Pix","Dinheiro","Cartão","Transferência","Outro"])
    with c2:
        # fiados em aberto desse cliente para escolher qual ID quitar
        abertos = df_base[(df_base.get("Cliente","")==cli) & (df_base.get("StatusFiado","")=="Em aberto")]
        ids_disp = abertos.get("IDLancFiado", pd.Series(dtype=str)).fillna("").tolist()
        id_sel = st.selectbox("IDLancFiado a quitar", options=ids_disp, help="Escolha o fiado em aberto deste cliente")
        valor_total = float(abertos[abertos["IDLancFiado"]==id_sel]["Valor"].sum()) if id_sel else 0.0
        st.metric("Valor do fiado selecionado", f"R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
        obs = st.text_input("Observação (opcional)", "")

    if st.button("Registrar pagamento", use_container_width=True, disabled=(not id_sel)):
        if not id_sel:
            st.error("Selecione um ID de fiado.")
        else:
            # 1) registrar pagamento no controle
            append_row(ABA_PAGT, [
                data_pag.strftime("%Y-%m-%d"), cli, valor_total, forma, id_sel, obs, gerar_id("P")
            ])
            # 2) atualizar Base: marcar fiado como Pago e criar linha normal (entra na receita)
            ss = conectar_sheets()
            ws_base = ss.worksheet(ABA_BASE)
            dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
            if dfb.empty:
                st.error("Base de Dados vazia.")
            else:
                mask = (dfb.get("IDLancFiado","") == id_sel) & (dfb.get("Cliente","")==cli)
                # guarda campos do serviço original
                if mask.any():
                    row = dfb[mask].iloc[0].copy()
                    serv = row.get("Serviço","")
                    tipo = row.get("Tipo","Serviço")
                    combo = row.get("Combo","")
                    func = row.get("Funcionário","")
                    fase = row.get("Fase","")
                    periodo = row.get("Período","")
                    valor = float(row.get("Valor", 0.0))

                    # marca como Pago (mas continua Conta=Fiado para não somar receita)
                    dfb.loc[mask, "StatusFiado"] = "Pago"

                    # cria nova linha normal na data do pagamento
                    novo = {
                        "Data": data_pag.strftime("%Y-%m-%d"),
                        "Serviço": serv,
                        "Valor": valor,
                        "Conta": forma,
                        "Cliente": cli,
                        "Combo": combo,
                        "Funcionário": func,
                        "Fase": fase,
                        "Tipo": tipo,
                        "Período": periodo,
                        "StatusFiado": "",           # linha normal
                        "IDLancFiado": id_sel,       # mantém referência
                        "VencimentoFiado": ""
                    }
                    for c in BASE_COLS_MIN + EXTRA_COLS:
                        if c not in dfb.columns: dfb[c] = None
                    dfb = pd.concat([dfb, pd.DataFrame([novo])], ignore_index=True)

                    salvar_df(ABA_BASE, dfb)
                    st.success(f"Pagamento registrado e fiado **{id_sel}** quitado para **{cli}**.")
                    st.cache_data.clear()
                else:
                    st.error("IDLancFiado não encontrado na Base de Dados.")

# =============== Em aberto & exportação ===============
else:
    st.subheader("📋 Fiados em aberto (a partir da Base de Dados)")
    if df_base.empty:
        st.info("Sem dados na Base.")
    else:
        em_aberto = df_base[df_base.get("StatusFiado","")=="Em aberto"].copy()
        if not em_aberto.empty and "Data" in em_aberto.columns:
            em_aberto["Data"] = pd.to_datetime(em_aberto["Data"], errors="coerce").dt.date
        st.dataframe(em_aberto.sort_values("Data", ascending=False), use_container_width=True, hide_index=True)

        total = float(em_aberto.get("Valor", pd.Series([0])).sum())
        st.metric("Total em aberto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
            (em_aberto.sort_values(["Cliente","Data"])).to_excel(w, index=False, sheet_name="FiadoEmAberto")
        st.download_button("⬇️ Exportar (Excel)", data=buf.getvalue(), file_name="fiado_em_aberto.xlsx")
