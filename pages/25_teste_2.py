# -*- coding: utf-8 -*-
# 12_Fiado.py — Fiado integrado à Base + Notificações Telegram (por funcionário + cópia p/ JP)
# - Combo por linhas com valores editáveis
# - Registrar pagamento por cliente (seleciona 1+ IDs; "selecionar todos")
# - Sugere última forma de pagamento do cliente (vinda da Base)
# - Quitar por COMPETÊNCIA (atualiza as linhas; não cria novas)
# - [REMOVIDO] bloco de lançar comissão 50% (feito em outra página)
# - Exportação Excel (openpyxl) ou CSV (fallback)
# - Sidebar expandida por padrão
# - Notificações Telegram roteadas p/ JPaulo e p/ Vinícius
# - Cópia privada p/ JPaulo ao quitar: comissões sugeridas + próxima terça p/ pagar

import streamlit as st
import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date, datetime, timedelta
from io import BytesIO
import pytz

# =========================
# TELEGRAM (idêntico ao 11_Adicionar_Atendimento.py)
# =========================
TELEGRAM_TOKEN_CONST = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_CONST = "493747253"
TELEGRAM_CHAT_ID_VINICIUS_CONST = "-1002953102982"  # canal do Vinícius já utilizado no 11_Adicionar

def _get_secret(name: str, default: str | None = None) -> str | None:
    try:
        val = st.secrets.get(name)
        val = (val or "").strip()
        if val:
            return val
    except Exception:
        pass
    return (default or "").strip() or None

def _get_token() -> str | None:
    return _get_secret("TELEGRAM_TOKEN", TELEGRAM_TOKEN_CONST)

def _get_chat_id_jp() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_JPAULO", TELEGRAM_CHAT_ID_JPAULO_CONST)

def _get_chat_id_vini() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_VINICIUS", TELEGRAM_CHAT_ID_VINICIUS_CONST)

def _check_tg_ready(token: str | None, chat_id: str | None) -> bool:
    return bool((token or "").strip() and (chat_id or "").strip())

def _chat_id_por_func(funcionario: str) -> str | None:
    if str(funcionario).strip() == "Vinicius":
        return _get_chat_id_vini()
    return _get_chat_id_jp()

def tg_send(text: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    if not _check_tg_ready(token, chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=30)
        js = r.json()
        return bool(r.ok and js.get("ok"))
    except Exception:
        return False

# =========================
# UTILS
# =========================
def proxima_terca(d: date) -> date:
    """Retorna a próxima TERÇA-FEIRA a partir de d (se for terça, retorna d)."""
    wd = d.weekday()  # Monday=0, Tuesday=1, ..., Sunday=6
    delta = (1 - wd) % 7
    return d + timedelta(days=delta)

# =========================
# APP
# =========================
st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide",
                   initial_sidebar_state="expanded")
st.title("💳 Controle de Fiado (combo por linhas + edição de valores)")

# ===== CONFIG =====
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_LANC = "Fiado_Lancamentos"
ABA_PAGT = "Fiado_Pagamentos"
TZ = pytz.timezone("America/Sao_Paulo")
DATA_FMT = "%d/%m/%Y"

BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
EXTRA_COLS    = ["StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"]

VALORES_PADRAO = {
    "Corte": 25.0, "Pezinho": 7.0, "Barba": 15.0, "Sobrancelha": 7.0,
    "Luzes": 45.0, "Pintura": 35.0, "Alisamento": 40.0, "Gel": 10.0, "Pomada": 15.0
}

# ===== Conexão =====
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
        if c not in df.columns:
            df[c] = ""
    df = df[[*BASE_COLS_MIN, *EXTRA_COLS, *[c for c in df.columns if c not in BASE_COLS_MIN+EXTRA_COLS]]]
    ws.clear()
    set_with_dataframe(ws, df)
    return ws

@st.cache_data
def carregar_tudo():
    ss = conectar_sheets()
    ws_base = garantir_base_cols(ss)
    ws_lanc = garantir_aba(ss, ABA_LANC,
        ["IDLanc","DataAtendimento","Cliente","Combo","Servicos","ValorTotal","Vencimento","Funcionario","Fase","Tipo","Periodo"])
    ws_pagt = garantir_aba(ss, ABA_PAGT,
        ["IDPagamento","IDLanc","DataPagamento","Cliente","FormaPagamento","ValorPago","Obs"])

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
        contas_raw = [c for c in dfb["Conta"].dropna().astype(str).str.strip().unique() if c]
        contas = sorted([c for c in contas_raw if c.lower() != "fiado"])
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
    if not combo_str:
        return []
    partes = [p.strip() for p in str(combo_str).split("+") if p.strip()]
    ajustadas = []
    for p in partes:
        hit = next((k for k in VALORES_PADRAO.keys() if k.lower() == p.lower()), p)
        ajustadas.append(hit)
    return ajustadas

def ultima_forma_pagto_cliente(df_base, cliente):
    if df_base.empty or not cliente:
        return None
    df = df_base[(df_base["Cliente"] == cliente) & (df_base["Conta"].str.lower() != "fiado")].copy()
    if df.empty:
        return None
    try:
        df["__d"] = pd.to_datetime(df["Data"], format=DATA_FMT, errors="coerce")
        df = df.sort_values("__d", ascending=False)
    except Exception:
        pass
    return str(df.iloc[0]["Conta"]) if not df.empty else None

# ===== Página =====
df_base, df_lanc, df_pagt, clientes, combos_exist, servs_exist, contas_exist = carregar_tudo()

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha:", ["➕ Lançar fiado","💰 Registrar pagamento","📋 Em aberto & exportação"])

# ---------- 1) Lançar fiado ----------
if acao == "➕ Lançar fiado":
    st.subheader("➕ Lançar fiado — cria UMA linha por serviço na Base (Conta='Fiado', StatusFiado='Em aberto')")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.selectbox("Cliente", options=[""] + clientes, index=0)
        if not cliente:
            cliente = st.text_input("Ou digite o nome do cliente", "")
        combo_str = st.selectbox("Combo (use 'corte+barba')", [""] + combos_exist)
        servico_unico = st.selectbox("Ou selecione um serviço (se não usar combo)", [""] + servs_exist)
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"], index=0)
    with c2:
        data_atend = st.date_input("Data do atendimento", value=date.today())
        venc = st.date_input("Vencimento (opcional)", value=date.today())
        fase = st.text_input("Fase", value="Dono + funcionário")
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"], index=0)
        periodo = st.selectbox("Período (opcional)", ["", "Manhã", "Tarde", "Noite"], index=0)

    servicos = parse_combo(combo_str) if combo_str else ([servico_unico] if servico_unico else [])
    valores_custom = {}
    if servicos:
        st.markdown("#### 💰 Edite os valores antes de salvar")
        for s in servicos:
            padrao = VALORES_PADRAO.get(s, 0.0)
            valores_custom[s] = st.number_input(
                f"{s} (padrão: R$ {padrao:.2f})", value=float(padrao), step=1.0, format="%.2f", key=f"valor_{s}"
            )

    if st.button("Salvar fiado", use_container_width=True):
        if not cliente:
            st.error("Informe o cliente.")
        elif not servicos:
            st.error("Informe combo ou um serviço.")
        else:
            idl = gerar_id("L")
            data_str = data_atend.strftime(DATA_FMT)
            venc_str = venc.strftime(DATA_FMT) if venc else ""

            novas = []
            for s in servicos:
                valor_item = float(valores_custom.get(s, VALORES_PADRAO.get(s, 0.0)))
                novas.append({
                    "Data": data_str, "Serviço": s, "Valor": valor_item, "Conta": "Fiado",
                    "Cliente": cliente, "Combo": combo_str if combo_str else "", "Funcionário": funcionario,
                    "Fase": fase, "Tipo": tipo, "Período": periodo,
                    "StatusFiado": "Em aberto", "IDLancFiado": idl, "VencimentoFiado": venc_str,
                    "DataPagamento": ""
                })

            ss = conectar_sheets()
            ws_base = ss.worksheet(ABA_BASE)
            dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")
            for c in BASE_COLS_MIN + EXTRA_COLS:
                if c not in dfb.columns:
                    dfb[c] = ""
            dfb = pd.concat([dfb, pd.DataFrame(novas)], ignore_index=True)
            salvar_df(ABA_BASE, dfb)

            total = float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum())
            append_row(ABA_LANC, [idl, data_str, cliente, combo_str, "+".join(servicos),
                                  total, venc_str, funcionario, fase, tipo, periodo])

            st.success(f"Fiado criado para **{cliente}** — ID: {idl}. Geradas {len(novas)} linhas na Base.")
            st.cache_data.clear()

            # ---- NOTIFICAÇÃO: novo fiado (roteado por funcionário)
            try:
                total_fmt = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                servicos_txt = "+".join(servicos) if servicos else (combo_str or "-")
                msg_html = (
                    "🧾 <b>Novo fiado criado</b>\n"
                    f"👤 Cliente: <b>{cliente}</b>\n"
                    f"🧰 Serviços: {servicos_txt}\n"
                    f"💵 Total: <b>{total_fmt}</b>\n"
                    f"📅 Atendimento: {data_str}\n"
                    f"⏳ Vencimento: {venc_str or '-'}\n"
                    f"🆔 ID: <code>{idl}</code>"
                )
                tg_send(msg_html, chat_id=_chat_id_por_func(funcionario))
            except Exception:
                pass

# ---------- 2) Registrar pagamento (COMPETÊNCIA) ----------
elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento — escolha o cliente e depois o(s) fiado(s) em aberto")

    df_abertos = df_base[df_base.get("StatusFiado", "") == "Em aberto"].copy()
    clientes_abertos = sorted(df_abertos["Cliente"].dropna().unique().tolist())

    colc1, colc2 = st.columns([1, 1])
    with colc1:
        cliente_sel = st.selectbox("Cliente com fiado em aberto", options=[""] + clientes_abertos, index=0)

    ultima = ultima_forma_pagto_cliente(df_base, cliente_sel) if cliente_sel else None
    lista_contas = contas_exist or ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"]
    default_idx = lista_contas.index(ultima) if (ultima in lista_contas) else 0
    with colc2:
        forma_pag = st.selectbox("Forma de pagamento (quitação)", options=lista_contas, index=default_idx)

    # IDs do cliente com rótulo amigável
    ids_opcoes = []
    if cliente_sel:
        grupo_cli = df_abertos[df_abertos["Cliente"] == cliente_sel].copy()
        grupo_cli["Data"] = pd.to_datetime(grupo_cli["Data"], errors="coerce").dt.strftime(DATA_FMT)
        grupo_cli["Valor"] = pd.to_numeric(grupo_cli["Valor"], errors="coerce").fillna(0)

        def atraso_max(idval):
            v = grupo_cli.loc[grupo_cli["IDLancFiado"] == idval, "VencimentoFiado"].dropna().astype(str)
            try:
                vdt = pd.to_datetime(v.iloc[0], format=DATA_FMT, errors="coerce").date() if not v.empty else None
            except Exception:
                vdt = None
            if vdt:
                d = (date.today() - vdt).days
                return d if d > 0 else 0
            return 0

        resumo_ids = (
            grupo_cli.groupby("IDLancFiado", as_index=False)
            .agg(Data=("Data", "min"), ValorTotal=("Valor", "sum"), Qtde=("Serviço", "count"), Combo=("Combo", "first"))
        )
        for _, r in resumo_ids.iterrows():
            atraso = atraso_max(r["IDLancFiado"])
            badge = "Em dia" if atraso <= 0 else f"{int(atraso)}d atraso"
            rotulo = f"{r['IDLancFiado']} • {r['Data']} • {int(r['Qtde'])} serv. • R$ {r['ValorTotal']:.2f} • {badge}"
            if pd.notna(r["Combo"]) and str(r["Combo"]).strip():
                rotulo += f" • {r['Combo']}"
            ids_opcoes.append((r["IDLancFiado"], rotulo))

    ids_valores = [i[0] for i in ids_opcoes]
    labels = {i: l for i, l in ids_opcoes}

    select_all = st.checkbox("Selecionar todos os fiados deste cliente", value=False, disabled=not bool(ids_valores))
    id_selecionados = st.multiselect(
        "Selecione 1 ou mais fiados do cliente",
        options=ids_valores,
        default=(ids_valores if select_all else []),
        format_func=lambda x: labels.get(x, x),
    )

    cold1, cold2 = st.columns([1, 1])
    with cold1:
        data_pag = st.date_input("Data do pagamento", value=date.today())
    with cold2:
        obs = st.text_input("Observação (opcional)", "")

    total_sel = 0.0
    funcs_envio = []  # funcionários envolvidos nos IDs selecionados (para roteamento Telegram)

    if id_selecionados:
        subset = df_abertos[df_abertos["IDLancFiado"].isin(id_selecionados)].copy()
        subset["Valor"] = pd.to_numeric(subset["Valor"], errors="coerce").fillna(0)
        total_sel = float(subset["Valor"].sum())

        st.info(
            f"Cliente: **{cliente_sel}** • IDs: {', '.join(id_selecionados)} • "
            f"Total: **R$ {total_sel:,.2f}**".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        resumo_srv = (
            subset.groupby("Serviço", as_index=False)
            .agg(Qtd=("Serviço", "count"), Total=("Valor", "sum"))
            .sort_values(["Qtd", "Total"], ascending=[False, False])
        )
        resumo_srv["Total"] = resumo_srv["Total"].map(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        st.caption("Resumo por serviço selecionado:")
        st.dataframe(resumo_srv, use_container_width=True, hide_index=True)

        # Quem está envolvido? (para roteamento de notificação no pagamento)
        funcs_envio = (
            subset["Funcionário"].dropna().astype(str).str.strip().str.lower().unique().tolist()
        )

    disabled_btn = not (cliente_sel and id_selecionados and forma_pag)
    if st.button("Registrar pagamento", use_container_width=True, disabled=disabled_btn):
        ss = conectar_sheets()
        ws_base = ss.worksheet(ABA_BASE)
        dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")

        if "DataPagamento" not in dfb.columns:
            dfb["DataPagamento"] = ""

        mask = dfb.get("IDLancFiado", "").isin(id_selecionados)
        if not mask.any():
            st.error("Nenhuma linha encontrada para os IDs selecionados.")
        else:
            subset_all = dfb[mask].copy()
            subset_all["Valor"] = pd.to_numeric(subset_all["Valor"], errors="coerce").fillna(0)
            total_pago = float(subset_all["Valor"].sum())

            # Atualiza no lugar (COMPETÊNCIA)
            dfb.loc[mask, "Conta"] = forma_pag
            dfb.loc[mask, "StatusFiado"] = "Pago"
            dfb.loc[mask, "VencimentoFiado"] = ""
            dfb.loc[mask, "DataPagamento"] = data_pag.strftime(DATA_FMT)

            salvar_df(ABA_BASE, dfb)

            append_row(
                ABA_PAGT,
                [
                    f"P-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}",
                    ";".join(id_selecionados),
                    data_pag.strftime(DATA_FMT),
                    cliente_sel,
                    forma_pag,
                    total_pago,
                    obs,
                ],
            )

            st.success(
                f"Pagamento registrado para **{cliente_sel}** (competência). "
                f"IDs quitados: {', '.join(id_selecionados)}. "
                f"Total: R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            st.cache_data.clear()

            # ---- NOTIFICAÇÃO: pagamento registrado (para cada funcionário envolvido)
            try:
                tot_fmt = f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                ids_txt = ", ".join(id_selecionados)
                msg_html = (
                    "✅ <b>Fiado quitado (competência)</b>\n"
                    f"👤 Cliente: <b>{cliente_sel}</b>\n"
                    f"💳 Forma: <b>{forma_pag}</b>\n"
                    f"💵 Total pago: <b>{tot_fmt}</b>\n"
                    f"📅 Data pagto: {data_pag.strftime(DATA_FMT)}\n"
                    f"🆔 IDs: <code>{ids_txt}</code>\n"
                    f"📝 Obs: {obs or '-'}"
                )
                destinos = set()
                for f in funcs_envio:
                    destinos.add(_chat_id_por_func(f.title()))  # 'vinicius' -> 'Vinicius'
                if not destinos:
                    destinos = { _get_chat_id_jp() }  # fallback: manda pra você
                for chat in destinos:
                    tg_send(msg_html, chat_id=chat)
            except Exception:
                pass

            # ---- CÓPIA PRIVADA PARA JPAULO: comissão sugerida + próxima terça
            try:
                sub = subset_all.copy()
                sub["Valor"] = pd.to_numeric(sub["Valor"], errors="coerce").fillna(0.0)

                grup = sub.groupby("Funcionário", dropna=True)["Valor"].sum().reset_index()
                itens_comissao = []
                total_comissao = 0.0
                for _, r in grup.iterrows():
                    func = str(r["Funcionário"]).strip()
                    if func.lower() == "jpaulo":
                        continue  # você não recebe comissão aqui
                    base = float(r["Valor"])
                    comiss = round(base * 0.50, 2)
                    total_comissao += comiss
                    itens_comissao.append(
                        f"• {func}: <b>R$ {comiss:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", ".")
                    )

                if itens_comissao:
                    dt_pgto = proxima_terca(data_pag)  # se terça, usa a mesma; para forçar a seguinte, some +1 dia
                    lista = "\n".join(itens_comissao)
                    msg_jp = (
                        "🧾 <b>Cópia para controle (comissão)</b>\n"
                        f"👤 Cliente: <b>{cliente_sel}</b>\n"
                        f"🗂️ IDs: <code>{', '.join(id_selecionados)}</code>\n"
                        f"📅 Pagamento em: <b>{data_pag.strftime(DATA_FMT)}</b>\n"
                        f"📌 Pagar comissão na próxima terça: <b>{dt_pgto.strftime(DATA_FMT)}</b>\n"
                        "------------------------------\n"
                        "💸 <b>Comissões sugeridas (50%)</b>\n"
                        f"{lista}\n"
                        "------------------------------\n"
                        f"💵 Total recebido: <b>R$ {total_pago:,.2f}</b>".replace(",", "X").replace(".", ",").replace("X", ".")
                    )
                    tg_send(msg_jp, chat_id=_get_chat_id_jp())
            except Exception:
                pass

# ---------- 3) Em aberto & exportação ----------
else:
    st.subheader("📋 Fiados em aberto (agrupados por ID)")
    if df_base.empty:
        st.info("Sem dados.")
    else:
        em_aberto = df_base[df_base.get("StatusFiado","") == "Em aberto"].copy()
        if em_aberto.empty:
            st.success("Nenhum fiado em aberto 🎉")
        else:
            colf1, colf2 = st.columns([2,1])
            with colf1:
                filtro_cliente = st.text_input("Filtrar por cliente (opcional)", "")
                if filtro_cliente.strip():
                    em_aberto = em_aberto[
                        em_aberto["Cliente"].str.contains(filtro_cliente.strip(), case=False, na=False)
                    ]
            with colf2:
                funcionarios_abertos = sorted(
                    em_aberto["Funcionário"].dropna().astype(str).unique().tolist()
                )
                filtro_func = st.selectbox("Filtrar por funcionário (opcional)", [""] + funcionarios_abertos)
                if filtro_func:
                    em_aberto = em_aberto[em_aberto["Funcionário"] == filtro_func]

            hoje = date.today()
            def parse_dt(x):
                try:
                    return datetime.strptime(str(x), DATA_FMT).date()
                except Exception:
                    return None
            em_aberto["__venc"] = em_aberto["VencimentoFiado"].apply(parse_dt)
            em_aberto["DiasAtraso"] = em_aberto["__venc"].apply(
                lambda d: (hoje - d).days if (d is not None and hoje > d) else 0
            )
            em_aberto["Situação"] = em_aberto["DiasAtraso"].apply(lambda n: "Em dia" if n<=0 else f"{int(n)}d atraso")

            em_aberto["Valor"] = pd.to_numeric(em_aberto["Valor"], errors="coerce").fillna(0)
            resumo = (
                em_aberto.groupby(["IDLancFiado","Cliente"], as_index=False)
                .agg(ValorTotal=("Valor","sum"), QtdeServicos=("Serviço","count"),
                     Combo=("Combo","first"), MaxAtraso=("DiasAtraso","max"))
            )
            resumo["Situação"] = resumo["MaxAtraso"].apply(lambda n: "Em dia" if n<=0 else f"{int(n)}d atraso")

            st.dataframe(
                resumo.sort_values(["MaxAtraso","ValorTotal"], ascending=[False, False])[[
                    "IDLancFiado","Cliente","ValorTotal","QtdeServicos","Combo","Situação"
                ]],
                use_container_width=True, hide_index=True
            )

            total = float(resumo["ValorTotal"].sum())
            st.metric("Total em aberto", f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

            try:
                from openpyxl import Workbook  # noqa
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_excel(
                        w, index=False, sheet_name="Fiado_Em_Aberto"
                    )
                st.download_button("⬇️ Exportar (Excel)", data=buf.getvalue(), file_name="fiado_em_aberto.xlsx")
            except Exception:
                csv_bytes = em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_csv(
                    index=False
                ).encode("utf-8-sig")
                st.download_button("⬇️ Exportar (CSV)", data=csv_bytes, file_name="fiado_em_aberto.csv")
