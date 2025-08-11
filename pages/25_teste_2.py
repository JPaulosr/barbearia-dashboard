# 12_Fiado.py — Fiado integrado à Base de Dados, com COMBO em múltiplas linhas
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date, datetime
from io import BytesIO
import pytz

st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide")
st.title("💳 Controle de Fiado (integrado à Base, com combo por linhas)")

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_LANC = "Fiado_Lancamentos"     # log de fiados (um por ID)
ABA_PAGT = "Fiado_Pagamentos"      # log de pagamentos
TZ = pytz.timezone("America/Sao_Paulo")

# === Colunas oficiais da Base (sem horários) + extras de fiado ===
BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
EXTRA_COLS    = ["StatusFiado","IDLancFiado","VencimentoFiado"]
DATA_FMT = "%d/%m/%Y"  # MESMO FORMATO do seu 3_Adicionar_Atendimento.py

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
    if not ws.row_values(1):
        ws.append_row(cols)
    return ws

def garantir_base_cols(ss):
    ws = garantir_aba(ss, ABA_BASE, BASE_COLS_MIN + EXTRA_COLS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    for c in BASE_COLS_MIN + EXTRA_COLS:
        if c not in df.columns: df[c] = ""
    # reordenar
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

    # clientes/combos/serviços existentes
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

# === Utils ===
def parse_combo(combo_str):
    # "corte+barba" -> ["corte","barba"]
    if not combo_str: return []
    return [p.strip() for p in str(combo_str).split("+") if p.strip()]

def saldo_em_aberto_cliente(df_base, cliente):
    if df_base.empty: return 0.0
    x = df_base[(df_base["Cliente"]==cliente) & (df_base["StatusFiado"]=="Em aberto")]
    return float(pd.to_numeric(x["Valor"], errors="coerce").fillna(0).sum()) if not x.empty else 0.0

# === Página ===
df_base, df_lanc, df_pagt, clientes, combos_exist, servs_exist, contas_exist = carregar_tudo()

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha:", ["➕ Lançar fiado (com combo)","💰 Registrar pagamento","📋 Em aberto & exportação"])

# ===================== Lançar Fiado =====================
if acao == "➕ Lançar fiado (com combo)":
    st.subheader("➕ Lançar fiado — grava na Base uma linha por serviço (Conta='Fiado', StatusFiado='Em aberto')")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.selectbox("Cliente", options=[""]+clientes, index=0)
        if not cliente:
            cliente = st.text_input("Ou digite o nome do cliente", "")
        combo = st.selectbox("Combo (use 'corte+barba')", [""] + combos_exist)
        servico_unico = st.selectbox("Ou selecione um serviço (se não usar combo)", [""] + servs_exist)
        valor_unico = st.number_input("Valor do serviço (R$)", min_value=0.0, step=1.0, format="%.2f")
        funcionario = st.selectbox("Funcionário", ["JPaulo","Vinicius"], index=0)
    with c2:
        data_atend = st.date_input("Data do atendimento", value=date.today())
        venc = st.date_input("Vencimento (opcional)", value=date.today())
        fase = st.text_input("Fase", value="Dono + funcionário")
        tipo = st.selectbox("Tipo", ["Serviço","Produto"], index=0)
        periodo = st.selectbox("Período (opcional)", ["","Manhã","Tarde","Noite"], index=0)

    if st.button("Salvar fiado", use_container_width=True):
        if not cliente:
            st.error("Informe o cliente.")
        else:
            idl = gerar_id("L")
            data_str = data_atend.strftime(DATA_FMT)
            venc_str = venc.strftime(DATA_FMT) if venc else ""

            # 1) Se combo informado -> cria UMA linha na Base por serviço; se não, usa serviço único
            novas = []
            servicos = parse_combo(combo) if combo else ([servico_unico] if servico_unico else [])
            if not servicos:
                st.error("Informe combo ou um serviço.")
            else:
                # Caixa para digitou valor por item? Aqui usamos um valor único se não combo.
                if combo:
                    st.warning("Este lançamento de FIADO vai criar uma linha por serviço do combo na Base. Valores devem ser informados individualmente no momento do atendimento (ou edite depois).")
                for s in servicos:
                    novas.append({
                        "Data": data_str,
                        "Serviço": s,
                        "Valor": valor_unico if not combo else "",  # pode deixar em branco se preferir editar depois
                        "Conta": "Fiado",
                        "Cliente": cliente,
                        "Combo": combo if combo else "",
                        "Funcionário": funcionario,
                        "Fase": fase,
                        "Tipo": tipo,
                        "Período": periodo,
                        "StatusFiado": "Em aberto",
                        "IDLancFiado": idl,
                        "VencimentoFiado": venc_str
                    })

                # Anexa na Base
                ss = conectar_sheets()
                ws_base = ss.worksheet(ABA_BASE)
                dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
                for c in BASE_COLS_MIN + EXTRA_COLS:
                    if c not in dfb.columns: dfb[c] = ""
                dfb = pd.concat([dfb, pd.DataFrame(novas)], ignore_index=True)
                salvar_df(ABA_BASE, dfb)

                # 2) Log do lançamento (1 linha por ID)
                valor_total = 0.0
                try:
                    valor_total = float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum())
                except:
                    pass
                append_row(ABA_LANC, [
                    idl, data_str, cliente, combo, "+".join(servicos), valor_total, venc_str, funcionario, fase, tipo, periodo
                ])

                st.success(f"Fiado criado para **{cliente}** — ID: {idl}. Foram geradas {len(novas)} linhas na Base (uma por serviço).")
                st.cache_data.clear()

# ===================== Registrar Pagamento =====================
elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento — quita TODAS as linhas da Base com o mesmo ID do fiado e cria linhas normais na data do pagamento")

    c1, c2 = st.columns(2)
    with c1:
        # IDs de fiados em aberto (group by IDLancFiado)
        abertos = df_base[df_base.get("StatusFiado","")=="Em aberto"].copy()
        ids = sorted([i for i in abertos.get("IDLancFiado", pd.Series([],dtype=str)).dropna().unique() if i])
        id_sel = st.selectbox("Selecione o ID do fiado (em aberto)", options=ids)
        forma = st.selectbox("Forma de pagamento", ["Pix","Dinheiro","Cartão","Transferência","Outro"])
    with c2:
        hoje = date.today()
        data_pag = st.date_input("Data do pagamento", value=hoje)
        obs = st.text_input("Observação (opcional)", "")

    if id_sel:
        grupo = abertos[abertos["IDLancFiado"]==id_sel].copy()
        cliente = grupo["Cliente"].iloc[0] if not grupo.empty else ""
        # resumo
        servicos = grupo["Serviço"].tolist()
        total = float(pd.to_numeric(grupo["Valor"], errors="coerce").fillna(0).sum())
        st.info(f"Cliente: **{cliente}** | Serviços: {', '.join(servicos)} | Total (somando linhas): **R$ {total:,.2f}**".replace(",", "X").replace(".", ",").replace("X","."))

    if st.button("Registrar pagamento", use_container_width=True, disabled=(not id_sel)):
        if not id_sel:
            st.error("Selecione um ID.")
        else:
            ss = conectar_sheets()
            # 1) Marca Base como Pago para todas as linhas daquele ID e cria LINHAS NORMAIS na data do pagamento (uma por serviço)
            ws_base = ss.worksheet(ABA_BASE)
            dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
            mask = dfb.get("IDLancFiado","") == id_sel
            if not mask.any():
                st.error("ID não encontrado na Base.")
            else:
                subset = dfb[mask].copy()
                cliente = subset["Cliente"].iloc[0] if not subset.empty else ""
                # marcar pago (mantém Conta=Fiado para histórico não financeiro)
                dfb.loc[mask, "StatusFiado"] = "Pago"

                # cria novas linhas normais (uma por serviço) com a forma real
                novas = []
                for _, r in subset.iterrows():
                    novas.append({
                        "Data": data_pag.strftime(DATA_FMT),
                        "Serviço": r.get("Serviço",""),
                        "Valor": r.get("Valor",""),
                        "Conta": forma,                    # agora entra na sua receita
                        "Cliente": r.get("Cliente",""),
                        "Combo": r.get("Combo",""),
                        "Funcionário": r.get("Funcionário",""),
                        "Fase": r.get("Fase",""),
                        "Tipo": r.get("Tipo","Serviço"),
                        "Período": r.get("Período",""),
                        "StatusFiado": "",                 # linha normal
                        "IDLancFiado": id_sel,             # mantém referência
                        "VencimentoFiado": ""
                    })
                dfb = pd.concat([dfb, pd.DataFrame(novas)], ignore_index=True)
                salvar_df(ABA_BASE, dfb)

                # 2) Log do pagamento
                append_row(ABA_PAGT, [
                    gerar_id("P"), id_sel, data_pag.strftime(DATA_FMT), cliente, forma, 
                    float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum()),
                    obs
                ])

                st.success(f"Pagamento registrado para **{cliente}**. Fiado **{id_sel}** quitado e linhas normais criadas ({len(novas)}).")
                st.cache_data.clear()

# ===================== Em aberto & exportação =====================
else:
    st.subheader("📋 Fiados em aberto (a partir da Base — agrupados por ID)")
    if df_base.empty:
        st.info("Sem dados.")
    else:
        em_aberto = df_base[df_base.get("StatusFiado","")=="Em aberto"].copy()
        if em_aberto.empty:
            st.success("Nenhum fiado em aberto 🎉")
        else:
            # grupo por ID e mostra resumo
            em_aberto["Valor"] = pd.to_numeric(em_aberto["Valor"], errors="coerce").fillna(0)
            resumo = (em_aberto
                      .groupby(["IDLancFiado","Cliente"], as_index=False)
                      .agg(ValorTotal=("Valor","sum"),
                           QtdeServicos=("Serviço","count"),
                           Combo=("Combo","first")))
            st.dataframe(resumo.sort_values("ValorTotal", ascending=False), use_container_width=True, hide_index=True)

            total = float(resumo["ValorTotal"].sum())
            st.metric("Total em aberto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
            # exportar linhas detalhadas
            buf = BytesIO()
            with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
                em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_excel(w, index=False, sheet_name="Fiado_Em_Aberto")
            st.download_button("⬇️ Exportar (Excel)", data=buf.getvalue(), file_name="fiado_em_aberto.xlsx")
