# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# Regras:
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - (Novo) Arredondamento para preço cheio por serviço (tabela) com tolerância.
# - (Novo) Benefício/Ajuste manual dentro do painel (entra no total e em Despesas).
# - (Opcional) Se pago no cartão, comissão calculada sobre TABELA (ignora desconto do cartão).

import streamlit as st
import pandas as pd
import gspread
import hashlib
import re
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz

# =============================
# CONFIG BÁSICA
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"

TZ = "America/Sao_Paulo"

# Colunas esperadas na Base de Dados
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    # Fiado
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"
]

# Colunas da aba Despesas
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]

# Percentual padrão da comissão
PERCENTUAL_PADRAO = 50.0

# Tabela de preços (valores CHEIOS por serviço)
VALOR_TABELA = {
    "Corte": 25.00,
    "Barba": 15.00,
    "Sobrancelha": 7.00,
    "Luzes": 45.00,
    "Tintura": 20.00,
    "Alisamento": 40.00,
    "Gel": 10.00,
    "Pomada": 15.00,
}

# =============================
# CONEXÃO SHEETS
# =============================
@st.cache_resource
def _conn():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    cred = Credentials.from_service_account_info(info, scopes=escopo)
    cli = gspread.authorize(cred)
    return cli.open_by_key(SHEET_ID)

def _ws(title: str):
    sh = _conn()
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=50)
        return ws

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").replace({pd.NA: ""})
    return df

def _write_df(title: str, df: pd.DataFrame):
    ws = _ws(title)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now():
    return datetime.now(pytz.timezone(TZ))

def parse_br_date(s: str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    return None

def to_br_date(dt: datetime):
    return dt.strftime("%d/%m/%Y")

def competencia_from_data_str(data_servico_str: str) -> str:
    dt = parse_br_date(data_servico_str)
    if not dt:
        return ""
    return dt.strftime("%m/%Y")

def janela_terca_a_segunda(terca_pagto: datetime):
    # terça de pagamento paga a semana ANTERIOR (terça→segunda)
    inicio = terca_pagto - timedelta(days=7)  # terça anterior
    fim = inicio + timedelta(days=6)          # segunda
    return inicio, fim

def make_refid(row: pd.Series) -> str:
    key = "|".join([
        str(row.get("Cliente", "")).strip(),
        str(row.get("Data", "")).strip(),
        str(row.get("Serviço", "")).strip(),
        str(row.get("Valor", "")).strip(),
        str(row.get("Funcionário", "")).strip(),
        str(row.get("Combo", "")).strip(),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def garantir_colunas(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df

def is_cartao(conta: str) -> bool:
    c = (conta or "").strip().lower()
    # cobre variações comuns: cartao, cartão, crédito, debito, maquininha, pos, etc
    padrao = r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)"
    return bool(re.search(padrao, c))

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    """
    Se habilitado, tenta 'grudar' o valor no preço CHEIO da TABELA do serviço,
    desde que esteja dentro da tolerância. Ex.: 23, 24.75, 25.10 → 25.00 (tol=2.00).
    Caso não haja valor de tabela para o serviço, arredonda para inteiro.
    """
    if not habilitado:
        return valor
    srv = (servico or "").strip()
    cheio = VALOR_TABELA.get(srv)
    if isinstance(cheio, (int, float)):
        if abs(valor - float(cheio)) <= tol:
            return float(cheio)
        # sem 'snap', mantém o valor original
        return valor
    # fallback: sem tabela, arredonda p/ inteiro (sem centavos) se dentro da tol de um inteiro "próximo"
    arred = round(valor)
    if abs(valor - arred) <= tol:
        return float(arred)
    return valor

def format_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

# Carrega base
base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs (linha 1)
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    if hoje.weekday() == 1:  # terça
        sugestao_terca = hoje
    else:
        delta = (1 - hoje.weekday()) % 7
        if delta == 0:
            delta = 7
        sugestao_terca = (hoje + timedelta(days=delta))
    terca_pagto = st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date())
    terca_pagto = datetime.combine(terca_pagto, datetime.min.time())

with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)

with colC:
    incluir_produtos = st.checkbox("Incluir PRODUTOS?", value=False)

# Inputs (linha 2)
meio_pag = st.selectbox("Meio de pagamento (para DESPESAS)", ["Dinheiro", "Pix", "Cartão", "Transferência"], index=0)
descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")

# Inputs (linha 3) — regras de cálculo
usar_tabela_cartao = st.checkbox(
    "Usar preço de TABELA para comissão quando pago no cartão",
    value=True,
    help="Ignora o valor líquido (com taxa) e comissiona pelo preço de tabela do serviço."
)
col_r1, col_r2 = st.columns([2,1])
with col_r1:
    arred_cheio = st.checkbox(
        "Arredondar para preço cheio de TABELA (tolerância abaixo)",
        value=True,
        help="Ex.: 23,00 / 24,75 / 25,10 → 25,00 (se dentro da tolerância)."
    )
with col_r2:
    tol_reais = st.number_input("Tolerância (R$)", value=2.00, step=0.50, min_value=0.0)

# ✅ Reprocessar esta terça (limpa/ignora cache desta terça)
reprocessar_terca = st.checkbox(
    "Reprocessar esta terça (regravar): ignorar/limpar cache desta terça antes de salvar",
    value=False,
    help="Marque se você apagou as linhas em Despesas e quer gravar novamente esta terça."
)

# Conjunto Vinicius
dfv = base[base["Funcionário"].astype(str).str.strip() == "Vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[dfv["Tipo"].astype(str).str.strip().str.lower() == "serviço"]
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

# Janela terça→segunda (anterior à terça de pagamento)
ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

# 1) Itens da SEMANA NÃO FIADO
mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((dfv["StatusFiado"].astype(str).str.strip() == "") |
     (dfv["StatusFiado"].astype(str).str.strip().str.lower() == "nao"))
)
semana_df = dfv[mask_semana].copy()

# 2) Fiados liberados até a terça (independe da data do serviço)
df_fiados = dfv[
    (dfv["StatusFiado"].astype(str).str.strip() != "") |
    (dfv["IDLancFiado"].astype(str).str.strip() != "")
].copy()
df_fiados["_dt_pagto"] = df_fiados["DataPagamento"].apply(parse_br_date)
fiados_liberados = df_fiados[(df_fiados["_dt_pagto"].notna()) & (df_fiados["_dt_pagto"] <= terca_pagto)].copy()

# Cache de comissões já pagas (por RefID)
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
cache = garantir_colunas(cache, cache_cols)

terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    # Ignora os pagos desta terça na visualização (permite reprocessar)
    ja_pagos = set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

# ------------------------------------
# Seção: Benefício / Ajuste manual
# ------------------------------------
st.markdown("---")
st.subheader("➕ Benefício / Ajuste manual (opcional)")
col_b1, col_b2, col_b3, col_b4 = st.columns([1,1,1,2])
with col_b1:
    ben_data = st.date_input("Data do benefício", value=br_now().date(), key="ben_data")
with col_b2:
    ben_valor = st.number_input("Valor (R$)", min_value=0.0, step=1.0, value=0.0, key="ben_valor")
with col_b3:
    ben_comp = (datetime(ben_data.year, ben_data.month, 1)).strftime("%m/%Y")
    st.text_input("Competência (auto)", value=ben_comp, key="ben_comp", disabled=True)
with col_b4:
    ben_desc = st.text_input("Descrição", value="Benefício/ajuste de comissão", key="ben_desc")

if st.button("💾 Adicionar benefício à lista desta terça"):
    if ben_valor <= 0:
        st.warning("Informe um valor de benefício maior que zero.")
    else:
        # Guardar em estado da sessão para somar com os itens da semana
        lista = st.session_state.get("beneficios_tmp", [])
        lista.append({
            "RefID": f"BEN|{ben_data.isoformat()}|{ben_valor:.2f}|{ben_desc.strip()}",
            "Data": ben_data.strftime("%d/%m/%Y"),
            "Competência": ben_comp,
            "ComissaoValor": float(ben_valor),
            "Observacao": f"Benefício — {ben_desc.strip()}",
        })
        st.session_state["beneficios_tmp"] = lista
        st.success(f"Benefício adicionado: {format_brl(ben_valor)} em {ben_data.strftime('%d/%m/%Y')}.")

# Função para montar grade editável e calcular comissões
def preparar_grid(df: pd.DataFrame, titulo: str, key_prefix: str):
    if df.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    df = df.copy()
    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos os itens de **{titulo}** já foram pagos.")
        return pd.DataFrame(), 0.0

    # Valor original e competência
    df["Valor_num"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    # Valor base para comissão:
    # 1) Se cartão + flag → usar TABELA
    # 2) Senão, aplicar 'snap' (arredondamento p/ CHEIO) se habilitado
    def _base_valor(row):
        serv = str(row.get("Serviço", "")).strip()
        conta = str(row.get("Conta", "")).strip()
        bruto = float(row.get("Valor_num", 0.0))
        if usar_tabela_cartao and is_cartao(conta):
            # comissão em cima do preço CHEIO da TABELA
            return float(VALOR_TABELA.get(serv, bruto))
        # snap opcional para valor cheio, mesmo quando não é cartão
        return snap_para_preco_cheio(serv, bruto, tol_reais, arred_cheio)

    df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)

    st.subheader(titulo)
    st.caption("Edite a % de comissão por linha, se precisar.")

    ed_cols = ["Data", "Cliente", "Serviço", "Valor_base_comissao", "Competência", "RefID"]
    ed = df[ed_cols].rename(columns={"Valor_base_comissao": "Valor (para comissão)"})
    ed["% Comissão"] = perc_padrao
    ed["Comissão (R$)"] = (ed["Valor (para comissão)"] * ed["% Comissão"] / 100.0).round(2)
    ed = ed.reset_index(drop=True)

    edited = st.data_editor(
        ed,
        key=f"editor_{key_prefix}",
        num_rows="fixed",
        column_config={
            "Valor (para comissão)": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Comissão": st.column_config.NumberColumn(format="%.1f %%", min_value=0.0, max_value=100.0, step=0.5),
            "Comissão (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        }
    )

    total = float(edited["Comissão (R$)"].sum())
    merged = df.merge(edited[["RefID", "% Comissão", "Comissão (R$)"]], on="RefID", how="left")
    merged["ComissaoValor"] = pd.to_numeric(merged["Comissão (R$)"], errors="coerce").fillna(0.0)

    st.success(f"Total de comissão em **{titulo}**: {format_brl(total)}")
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados")

# Adiciona BENEFÍCIOS temporários (se houver)
beneficios_tmp = st.session_state.get("beneficios_tmp", [])
if beneficios_tmp:
    st.info(f"{len(beneficios_tmp)} benefício(s) adicionados nesta sessão:")
    for b in beneficios_tmp:
        st.write(f"- {b['Data']} • {b['Observacao']} • {format_brl(b['ComissaoValor'])}")

total_geral = total_semana + total_fiados + sum(b["ComissaoValor"] for b in beneficios_tmp)
st.header(f"💵 Total desta terça (consolidado): {format_brl(total_geral)}")

# =============================
# CONFIRMAR E GRAVAR
# =============================
if st.button("✅ Registrar comissão (por DIA do atendimento) + benefícios e marcar itens como pagos"):
    if ((semana_grid is None or semana_grid.empty) and
        (fiados_grid is None or fiados_grid.empty) and
        (len(beneficios_tmp) == 0)):
        st.warning("Não há itens para pagar.")
    else:
        # 1) Atualiza cache item a item (para não pagar duas vezes)
        novos_cache = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty:
                continue
            for _, r in df_part.iterrows():
                novos_cache.append({
                    "RefID": r["RefID"],
                    "PagoEm": to_br_date(br_now()),
                    "TerçaPagamento": to_br_date(terca_pagto),
                    "ValorComissao": f'{r["ComissaoValor"]:.2f}'.replace(".", ","),
                    "Competencia": r.get("Competência", ""),
                    "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
                })

        # Benefícios entram no cache com RefID próprio
        for b in beneficios_tmp:
            novos_cache.append({
                "RefID": b["RefID"],
                "PagoEm": to_br_date(br_now()),
                "TerçaPagamento": to_br_date(terca_pagto),
                "ValorComissao": f'{b["ComissaoValor"]:.2f}'.replace(".", ","),
                "Competencia": b["Competência"] if "Competência" in b else b["Competência"] if "Competência" in b else "",
                "Observacao": b["Observacao"],
            })

        cache_df = _read_df(ABA_COMISSOES_CACHE)
        cache_df = garantir_colunas(cache_df, cache_cols)

        if reprocessar_terca:
            # remove do cache tudo desta terça selecionada e regrava do zero
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)].copy()

        cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
        _write_df(ABA_COMISSOES_CACHE, cache_upd)

        # 2) Lança em DESPESAS: UMA LINHA POR DIA DO ATENDIMENTO + benefícios
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)
        for c in COLS_DESPESAS_FIX:
            if c not in despesas_df.columns:
                despesas_df[c] = ""

        # Junta itens pagáveis com Data do serviço, Competência e valor da comissão
        pagaveis = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty:
                continue
            pagaveis.append(df_part[["Data", "Competência", "ComissaoValor"]].copy())

        # Benefícios são adicionados com a própria "Data"
        if beneficios_tmp:
            ben_df = pd.DataFrame([
                {"Data": b["Data"], "Competência": b.get("Competência", ""), "ComissaoValor": b["ComissaoValor"]}
                for b in beneficios_tmp
            ])
            pagaveis.append(ben_df)

        linhas = []
        if pagaveis:
            pagos = pd.concat(pagaveis, ignore_index=True)

            def _norm_dt(s):
                s = (s or "").strip()
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(s, fmt)
                    except Exception:
                        pass
                return None

            pagos["_dt"] = pagos["Data"].apply(_norm_dt)
            pagos = pagos[pagos["_dt"].notna()].copy()

            por_dia = pagos.groupby(["Data", "Competência"], dropna=False)["ComissaoValor"].sum().reset_index()

            for _, row in por_dia.iterrows():
                data_serv = str(row["Data"]).strip()            # dd/mm/aaaa do atendimento/benefício
                comp      = str(row["Competência"]).strip()     # mm/aaaa
                val       = float(row["ComissaoValor"])

                linhas.append({
                    "Data": data_serv,  # ✅ Data do atendimento ou do benefício
                    "Prestador": "Vinicius",
                    "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {to_br_date(terca_pagto)}",
                    "Valor": f'R$ {val:.2f}'.replace(".", ","),
                    "Me Pag:": meio_pag
                })

        if linhas:
            despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
            colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                             [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
            despesas_final = despesas_final[colunas_finais]
            _write_df(ABA_DESPESAS, despesas_final)

            # Limpa os benefícios temporários da sessão
            st.session_state["beneficios_tmp"] = []

            st.success(
                f"🎉 Comissão registrada! {len(linhas)} linha(s) adicionada(s) em **{ABA_DESPESAS}** "
                f"(uma por DIA/benefício) e {len(novos_cache)} itens marcados no **{ABA_COMISSOES_CACHE}**."
            )
            st.balloons()
        else:
            st.warning("Não há valores a lançar em Despesas.")
