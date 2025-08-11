# 12_Fiado.py — Fiado integrado à Base, com COMBO por linhas, edição de valores e 3 modos de operação
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date, datetime
from io import BytesIO
import pytz

st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide")
st.title("💳 Controle de Fiado (combo por linhas + edição de valores)")

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_LANC = "Fiado_Lancamentos"     # log por ID
ABA_PAGT = "Fiado_Pagamentos"      # log de pagamento
TZ = pytz.timezone("America/Sao_Paulo")
DATA_FMT = "%d/%m/%Y"  # igual ao seu 3_Adicionar_Atendimento.py

# Colunas oficiais da Base + extras
BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
EXTRA_COLS    = ["StatusFiado","IDLancFiado","VencimentoFiado"]

# Tabela de valores padrão (ajuste à vontade)
VALORES_PADRAO = {
    "Corte": 25.0,
    "Pezinho": 7.0,
    "Barba": 15.0,
    "Sobrancelha": 7.0,
    "Luzes": 45.0,
    "Pintura": 35.0,
    "Alisamento": 40.0,
    "Gel": 10.0,
    "Pomada": 15.0,
}

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
    if not ws.row_values(1):
        ws.append_row(cols)
    return ws

def garantir_base_cols(ss):
    ws = garantir_aba(ss, ABA_BASE, BASE_COLS_MIN + EXTRA_COLS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    for c in BASE_COLS_MIN + EXTRA_COLS:
        if c not in df.columns: df[c] = ""
    df = df[[*BASE_COLS_MIN, *EXTRA_COLS, *[c for c in df.columns if c not in BASE_COLS_MIN+EXTRA_COLS]]]
    ws.clear()
    set_with_dataframe(ws, df)
    return ws

@st.cache_data
def carregar_tudo():
    ss = conectar_sheets()
    ws_base = garantir_base_cols(ss)
    ws_lanc = garantir_aba(ss, ABA_LANC, ["IDLanc","DataAtendimento","Cliente","Combo","Servicos","ValorTotal","Vencimento","Funcionario","Fase","Tipo","Periodo"])
    ws_pagt = garantir_aba(ss, ABA_PAGT, ["IDPagamento","IDLanc","DataPagamento","Cliente","FormaPagamento","ValorPago","Obs"])

    df_base = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
    df_lanc = get_as_dataframe(ws_lanc, evaluate_formulas=True, header=0).dropna(how="all")
    df_pagt = get_as_dataframe(ws_pagt, evaluate_formulas=True, header=0).dropna(how="all")

    # listas para selects
    try:
        dfb = df_base.copy()
        dfb["Cliente"] = dfb["Cliente"].astype(str).str.strip()
        clientes = sorted([c for c in dfb["Cliente"].dropna().unique() if c])
        combos  = sorted([c for c in dfb["Combo"].dropna().unique() if c])
        servs   = sorted([s for s in dfb["Serviço"].dropna().unique() if s])
        contas  = sorted([c for c in dfb["Conta"].dropna().unique() if c])
    except Exception:
        clientes, combos, servs, contas = [], [], [], []
    return df_base, df_lanc, df_pagt, clientes, combos, servs, contas

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

def parse_combo(combo_str):
    # "corte+barba" -> ["Corte","Barba"] com capitalização do dicionário, se existir
    if not combo_str: return []
    partes = [p.strip() for p in str(combo_str).split("+") if p.strip()]
    ajustadas = []
    for p in partes:
        hit = next((k for k in VALORES_PADRAO.keys() if k.lower() == p.lower()), p)
        ajustadas.append(hit)
    return ajustadas

# =================== Página (3 modos) ===================
df_base, df_lanc, df_pagt, clientes, combos_exist, servs_exist, contas_exist = carregar_tudo()

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha:", ["➕ Lançar fiado","💰 Registrar pagamento","📋 Em aberto & exportação"])

# ---------- 1) Lançar fiado ----------
if acao == "➕ Lançar fiado":
    st.subheader("➕ Lançar fiado — cria UMA linha por serviço na Base (Conta='Fiado', StatusFiado='Em aberto')")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.selectbox("Cliente", options=[""]+clientes, index=0)
        if not cliente:
            cliente = st.text_input("Ou digite o nome do cliente", "")
        combo_str = st.selectbox("Combo (use 'corte+barba')", [""] + combos_exist)
        servico_unico = st.selectbox("Ou selecione um serviço (se não usar combo)", [""] + servs_exist)
        funcionario = st.selectbox("Funcionário", ["JPaulo","Vinicius"], index=0)
    with c2:
        data_atend = st.date_input("Data do atendimento", value=date.today())
        venc = st.date_input("Vencimento (opcional)", value=date.today())
        fase = st.text_input("Fase", value="Dono + funcionário")
        tipo = st.selectbox("Tipo", ["Serviço","Produto"], index=0)
        periodo = st.selectbox("Período (opcional)", ["","Manhã","Tarde","Noite"], index=0)

    # editor de valores por serviço
    servicos = parse_combo(combo_str) if combo_str else ([servico_unico] if servico_unico else [])
    valores_custom = {}
    if servicos:
        st.markdown("#### 💰 Edite os valores antes de salvar")
        for s in servicos:
            padrao = VALORES_PADRAO.get(s, 0.0)
            valores_custom[s] = st.number_input(f"{s} (padrão: R$ {padrao:.2f})",
                                                value=float(padrao), step=1.0, format="%.2f", key=f"valor_{s}")

    if st.button("Salvar fiado", use_container_width=True):
        if not cliente:
            st.error("Informe o cliente.")
        elif not servicos:
            st.error("Informe combo ou um serviço.")
        else:
            idl = gerar_id("L")
            data_str = data_atend.strftime(DATA_FMT)
            venc_str = venc.strftime(DATA_FMT) if venc else ""

            # Base: cria uma linha por serviço com valores editados
            novas = []
            for s in servicos:
                valor_item = float(valores_custom.get(s, VALORES_PADRAO.get(s, 0.0)))
                novas.append({
                    "Data": data_str,
                    "Serviço": s,
                    "Valor": valor_item,
                    "Conta": "Fiado",
                    "Cliente": cliente,
                    "Combo": combo_str if combo_str else "",
                    "Funcionário": funcionario,
                    "Fase": fase,
                    "Tipo": tipo,
                    "Período": periodo,
                    "StatusFiado": "Em aberto",
                    "IDLancFiado": idl,
                    "VencimentoFiado": venc_str
                })

            ss = conectar_sheets()
            ws_base = ss.worksheet(ABA_BASE)
            dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
            for c in BASE_COLS_MIN + EXTRA_COLS:
                if c not in dfb.columns: dfb[c] = ""
            dfb = pd.concat([dfb, pd.DataFrame(novas)], ignore_index=True)
            salvar_df(ABA_BASE, dfb)

            # Log do lançamento (uma linha por ID com total)
            valor_total = float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum())
            append_row(ABA_LANC, [
                idl, data_str, cliente, combo_str, "+".join(servicos), valor_total, venc_str, funcionario, fase, tipo, periodo
            ])

            st.success(f"Fiado criado para **{cliente}** — ID: {idl}. Geradas {len(novas)} linhas na Base.")
            st.cache_data.clear()

# ---------- 2) Registrar pagamento ----------
elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento — quita todas as linhas do mesmo ID e cria linhas normais na data do pagamento")

    # IDs em aberto
    abertos = df_base[df_base.get("StatusFiado","")=="Em aberto"].copy()
    ids = sorted([i for i in abertos.get("IDLancFiado", pd.Series([],dtype=str)).dropna().unique() if i])

    c1, c2 = st.columns(2)
    with c1:
        id_sel = st.selectbox("Selecione o ID do fiado (em aberto)", options=ids)
        forma = st.selectbox("Forma de pagamento", ["Pix","Dinheiro","Cartão","Transferência","Outro"])
    with c2:
        data_pag = st.date_input("Data do pagamento", value=date.today())
        obs = st.text_input("Observação (opcional)", "")

    if id_sel:
        grupo = abertos[abertos["IDLancFiado"]==id_sel].copy()
        cliente = grupo["Cliente"].iloc[0] if not grupo.empty else ""
        grupo["Valor"] = pd.to_numeric(grupo["Valor"], errors="coerce").fillna(0)
        total = float(grupo["Valor"].sum())
        st.info(f"Cliente: **{cliente}** | Serviços: {', '.join(grupo['Serviço'].tolist())} | Total: **R$ {total:,.2f}**".replace(",", "X").replace(".", ",").replace("X","."))

    if st.button("Registrar pagamento", use_container_width=True, disabled=(not id_sel)):
        ss = conectar_sheets()
        # 1) Atualiza Base: marca pago e cria linhas normais (uma por serviço)
        ws_base = ss.worksheet(ABA_BASE)
        dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
        mask = dfb.get("IDLancFiado","") == id_sel
        if not mask.any():
            st.error("ID não encontrado na Base.")
        else:
            subset = dfb[mask].copy()
            cliente = subset["Cliente"].iloc[0] if not subset.empty else ""

            # marca como Pago (histórico do fiado)
            dfb.loc[mask, "StatusFiado"] = "Pago"

            # cria novas linhas normais (entram na receita)
            novas = []
            for _, r in subset.iterrows():
                novas.append({
                    "Data": data_pag.strftime(DATA_FMT),
                    "Serviço": r.get("Serviço",""),
                    "Valor": r.get("Valor",""),
                    "Conta": forma,
                    "Cliente": r.get("Cliente",""),
                    "Combo": r.get("Combo",""),
                    "Funcionário": r.get("Funcionário",""),
                    "Fase": r.get("Fase",""),
                    "Tipo": r.get("Tipo","Serviço"),
                    "Período": r.get("Período",""),
                    "StatusFiado": "",
                    "IDLancFiado": id_sel,
                    "VencimentoFiado": ""
                })
            dfb = pd.concat([dfb, pd.DataFrame(novas)], ignore_index=True)
            salvar_df(ABA_BASE, dfb)

            # 2) Log do pagamento
            total_pago = float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum())
            append_row(ABA_PAGT, [f"P-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}", id_sel,
                                  data_pag.strftime(DATA_FMT), cliente, forma, total_pago, obs])

            st.success(f"Pagamento registrado para **{cliente}**. Fiado **{id_sel}** quitado ({len(novas)} linhas criadas).")
            st.cache_data.clear()

# ---------- 3) Em aberto & exportação ----------
else:
    st.subheader("📋 Fiados em aberto (agrupados por ID)")
    if df_base.empty:
        st.info("Sem dados.")
    else:
        "count"),
                           Combo=("Combo","first")))
            st.dataframe(resumo.sort_values("ValorTotal", ascending=False), use_container_width=True, hide_index=True)

            total = float(resumo["ValorTotal"].sum())
            st.metric("Total em aberto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_excel(w, index=False, sheet_name="Fiado_Em_Aberto")
            st.download_button("⬇️ Exportar (Excel)", data=buf.getvalue(), file_name="fiado_em_aberto.xlsx")
