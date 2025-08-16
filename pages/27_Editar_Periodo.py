# 15_Editar_Periodo.py — Edição em LOTE do "Período" por DIA com checklist
# - Filtra por DIA
# - Exibe TODOS os clientes daquele dia com:
#     • checkbox (Selecionar)
#     • Período atual (ou "—" se vazio)
#     • Quantas linhas (para saber se o cliente tem mais de um registro no dia)
#     • Status (Sem período / Definido / Misto)
# - Ferramentas: Buscar por nome, Selecionar todos, Só sem período, Inverter, Limpar
# - Aplica o Período somente aos clientes selecionados (todas as linhas do cliente no dia)
# - Atualiza por batch no Google Sheets (rápido e seguro)
# --------------------------------------------------------------

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import date

st.set_page_config(page_title="Editar Período (Lote)", page_icon="🕒", layout="wide")
st.title("🕒 Editar Período por Data — Seleção por Cliente")

# =========================
# CONFIG — ajuste se necessário
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"  # sua planilha
BASE_ALVOS = [
    "Base de Dados", "base de dados", "BASE DE DADOS",
    "Base de Dados Masculino", "Base de Dados - Masculino",
    "Base de Dados Feminino", "Base de Dados - Feminino"
]
DATA_COL = "Data"
CLIENTE_COL = "Cliente"
PERIODO_COL = "Período"  # troque para "Periodo" se na planilha não houver acento

# =========================
# CONEXÃO GOOGLE SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets.get("gcp_service_account") or st.secrets.get("GCP_SERVICE_ACCOUNT")
    if not info:
        st.error("❌ Secrets ausentes. Adicione 'gcp_service_account' nos Secrets do Streamlit.")
        st.stop()
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

def abrir_aba_base(gc):
    sh = gc.open_by_key(SHEET_ID)
    for nome in BASE_ALVOS:
        try:
            return sh.worksheet(nome)
        except Exception:
            pass
    nomes = [w.title for w in sh.worksheets()]
    st.error(f"❌ Aba da Base não encontrada. Ajuste BASE_ALVOS. Abas disponíveis: {nomes}")
    st.stop()

@st.cache_data(ttl=120)
def carregar_base():
    gc = conectar_sheets()
    ws = abrir_aba_base(gc)
    df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str)
    df = df.dropna(how="all").reset_index(drop=True)
    df = df.loc[:, ~df.columns.isnull()]
    df.columns = [str(c).strip() for c in df.columns]

    faltando = [c for c in [DATA_COL, CLIENTE_COL] if c not in df.columns]
    if faltando:
        st.error(f"❌ Colunas ausentes na base: {faltando}. Ajuste DATA_COL/CLIENTE_COL.")
        st.stop()

    if PERIODO_COL not in df.columns:
        df[PERIODO_COL] = ""

    # Parser de data robusto
    def to_date(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return pd.to_datetime(x, format=fmt, dayfirst=True)
            except Exception:
                pass
        return pd.to_datetime(x, dayfirst=True, errors="coerce")

    df["_DataDT"] = df[DATA_COL].apply(to_date)
    df["_row_number"] = df.index + 2  # 1 cabeçalho + 1 offset de índice
    return df

def get_ws():
    gc = conectar_sheets()
    return abrir_aba_base(gc)

# =========================
# UI — filtros
# =========================
df = carregar_base()
dia = st.date_input("📅 Selecione o DIA", value=date.today(), format="DD/MM/YYYY")
df_dia = df[df["_DataDT"].dt.date == pd.to_datetime(dia).date()].copy()

if df_dia.empty:
    st.info("Nenhum registro para este dia.")
    st.stop()

# =========================
# Resumo por Cliente no dia
# =========================
# agregamos período por cliente para exibir status atual
def resumo_cliente(grp: pd.DataFrame) -> pd.Series:
    # valores distintos de período (limpos)
    ps = grp[PERIODO_COL].fillna("").astype(str).str.strip()
    distintos = sorted(set(ps))
    # remove vazio apenas para testar "definido"
    definidos = [p for p in distintos if p != ""]
    if len(definidos) == 0:
        status = "Sem período"
        periodo_view = "—"
    elif len(definidos) == 1 and (("" not in distintos) or (len(distintos) == 1)):
        status = "Definido"
        periodo_view = definidos[0]
    else:
        status = "Misto"
        # mostra todos para transparência
        periodo_view = ", ".join([p if p != "" else "—" for p in distintos])
    return pd.Series({
        "Linhas": len(grp),
        "PeriodoAtual": periodo_view,
        "Status": status
    })

sum_por_cliente = df_dia.groupby(CLIENTE_COL, dropna=True).apply(resumo_cliente).reset_index(names=[CLIENTE_COL])
sum_por_cliente.insert(0, "Selecionar", False)  # checkbox padrão
sum_por_cliente = sum_por_cliente.sort_values([ "Status", CLIENTE_COL ]).reset_index(drop=True)

# =========================
# Ferramentas de seleção
# =========================
st.markdown("### ✅ Selecione os clientes que deseja atualizar")

busca = st.text_input("🔎 Buscar cliente (contém):", value="", placeholder="digite parte do nome...")
view = sum_por_cliente.copy()
if busca.strip():
    s = busca.strip().lower()
    view = view[view[CLIENTE_COL].str.lower().str.contains(s)].reset_index(drop=True)

col_bts = st.columns(4)
with col_bts[0]:
    if st.button("Selecionar TODOS", use_container_width=True):
        view["Selecionar"] = True
with col_bts[1]:
    if st.button("Somente SEM PERÍODO", use_container_width=True):
        view["Selecionar"] = view["Status"].eq("Sem período")
with col_bts[2]:
    if st.button("Inverter seleção (visíveis)", use_container_width=True):
        view["Selecionar"] = ~view["Selecionar"]
with col_bts[3]:
    if st.button("Limpar seleção", use_container_width=True):
        view["Selecionar"] = False

# Editor com checkbox
edit = st.data_editor(
    view,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Selecionar": st.column_config.CheckboxColumn(help="Marque para incluir na atualização em lote."),
        "PeriodoAtual": st.column_config.TextColumn("Período atual"),
        "Status": st.column_config.TextColumn(help="Sem período / Definido / Misto"),
        "Linhas": st.column_config.NumberColumn(format="%d")
    },
    disabled=["PeriodoAtual", "Status", "Linhas", CLIENTE_COL],  # só edita o checkbox
    num_rows="fixed",
    key="editor_periodo_dia"
)

# Lista final de selecionados (apenas do que está visível e marcado)
clientes_selecionados = edit.loc[edit["Selecionar"], CLIENTE_COL].tolist()

# Mostra um preview das linhas que serão afetadas
if clientes_selecionados:
    st.markdown("#### 🔎 Prévia das linhas que serão atualizadas")
    prev = df_dia[df_dia[CLIENTE_COL].isin(clientes_selecionados)][[DATA_COL, CLIENTE_COL, PERIODO_COL]]
    st.dataframe(prev.sort_values([CLIENTE_COL, DATA_COL]), use_container_width=True, hide_index=True)
else:
    st.info("Selecione um ou mais clientes acima para ver a prévia.")

# =========================
# Escolha de Período e Aplicar
# =========================
st.markdown("### 🛠️ Aplicar Período (lote nos selecionados)")
colp1, colp2 = st.columns([2, 3])
with colp1:
    periodo_opcao = st.radio(
        "Período a aplicar",
        options=["Manhã", "Tarde", "Noite", "Integral", "Outro"],
        horizontal=True
    )
with colp2:
    periodo_outro = st.text_input("Se 'Outro', especifique:", value="", placeholder="ex.: Almoço, Pós-Serviço…")

periodo_final = periodo_outro.strip() if periodo_opcao == "Outro" else periodo_opcao

def aplicar_periodo_em_lote(clientes_sel, novo_periodo):
    if not clientes_sel:
        return 0
    ws = get_ws()

    # pega índice da coluna PERÍODO (ou cria)
    header = ws.row_values(1)
    try:
        col_idx = header.index(PERIODO_COL) + 1
    except ValueError:
        ws.update_cell(1, len(header) + 1, PERIODO_COL)
        col_idx = len(header) + 1

    # linhas alvo (todas as linhas dos clientes selecionados neste dia)
    alvo = df_dia[df_dia[CLIENTE_COL].isin(clientes_sel)]
    if alvo.empty:
        return 0

    data = []
    for r in alvo["_row_number"].tolist():
        a1 = gspread.utils.rowcol_to_a1(r, col_idx)
        data.append({"range": a1, "values": [[novo_periodo]]})

    # batch em chunks
    total = 0
    for i in range(0, len(data), 500):
        ws.batch_update(data[i:i+500], value_input_option="USER_ENTERED")
        total += len(data[i:i+500])
    return total

col_apply1, col_apply2 = st.columns([1, 3])
with col_apply1:
    aplicar = st.button("✅ Aplicar aos selecionados", type="primary", use_container_width=True)
with col_apply2:
    st.caption("Atualiza todas as linhas dos clientes **marcados** neste dia.")

if aplicar:
    if not clientes_selecionados:
        st.error("Selecione ao menos 1 cliente.")
    elif periodo_final.strip() == "":
        st.error("Informe um valor para o Período.")
    else:
        qtd = aplicar_periodo_em_lote(clientes_selecionados, periodo_final.strip())
        if qtd > 0:
            st.success(f"✅ {qtd} célula(s) atualizada(s) com Período = **{periodo_final}**.")
            st.cache_data.clear()
            st.toast("Base recarregada. Atualize a página para ver as mudanças.", icon="✅")
        else:
            st.info("Nenhuma linha alterada (verifique seleção e dia).")

# =========================
# Ação rápida (opcional): marcar TODOS os visíveis
# =========================
st.divider()
st.subheader("⚡ Ação rápida (opcional)")
colq1, colq2, colq3 = st.columns([2,2,2])
with colq1:
    periodo_rapido = st.selectbox("Marcar TODOS os **visíveis** como:", ["", "Manhã", "Tarde", "Noite", "Integral", "Outro"])
with colq2:
    periodo_rapido_outro = st.text_input("Se 'Outro', especifique (ação rápida):", value="")
with colq3:
    if st.button("Aplicar (visíveis)", use_container_width=True):
        if periodo_rapido == "":
            st.error("Escolha um período para a ação rápida.")
        else:
            valor = periodo_rapido_outro.strip() if periodo_rapido == "Outro" else periodo_rapido
            if valor == "":
                st.error("Informe o texto do período (Outro).")
            else:
                # aplica somente aos clientes atualmente visíveis na tabela (filtro de busca)
                visiveis = edit[CLIENTE_COL].tolist()
                qtd = aplicar_periodo_em_lote(visiveis, valor)
                if qtd > 0:
                    st.success(f"✅ {qtd} célula(s) atualizada(s) para **{valor}** (clientes visíveis).")
                    st.cache_data.clear()
                else:
                    st.info("Nenhuma linha alterada.")
