import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime, timedelta
import pytz

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_COMISSOES = "Comissões"
ABA_DESPESAS = "Despesas"

TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

VALOR_TABELA = {
    "Corte": 25.0,
    "Pezinho": 7.0,
    "Barba": 15.0,
    "Sobrancelha": 7.0,
    "Luzes": 45.0,
    "Tintura": 20.0,
    "Alisamento": 40.0,
    "Gel": 10.0,
    "Pomada": 15.0,
}

# =========================
# UTILS
# =========================
def to_br_date(dt: datetime | str) -> str:
    if isinstance(dt, str):
        return dt
    return dt.strftime(DATA_FMT)

def now_br() -> str:
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def snap_para_preco_cheio(servico: str, bruto: float, tol: float, arred: bool) -> float:
    alvo = VALOR_TABELA.get(servico, bruto)
    if abs(bruto - alvo) <= tol:
        return alvo
    return round(bruto) if arred else bruto

def _refid_despesa(data_str: str, prest: str, desc: str, valor: float, meio: str) -> str:
    raw = f"{data_str}-{prest}-{desc}-{valor:.2f}-{meio}"
    return str(abs(hash(raw)))[:12]

# =========================
# SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def carregar_df(aba_nome):
    aba = conectar_sheets().worksheet(aba_nome)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    return df, aba

def salvar_df(aba_nome, df_final: pd.DataFrame):
    aba = conectar_sheets().worksheet(aba_nome)
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

# =========================
# APP
# =========================
st.set_page_config(layout="wide")
st.title("💈 Comissão Vinícius")

df_base, _ = carregar_df(ABA_COMISSOES)
df_desp, _ = carregar_df(ABA_DESPESAS)

# filtros
data_ini = st.date_input("Data inicial", value=datetime.today() - timedelta(days=7))
data_fim = st.date_input("Data final", value=datetime.today())
data_ini_str, data_fim_str = to_br_date(data_ini), to_br_date(data_fim)

base_jan_vini = df_base[
    (df_base["Funcionário"] == "Vinicius")
    & (df_base["Data"] >= data_ini_str)
    & (df_base["Data"] <= data_fim_str)
].copy()

if base_jan_vini.empty:
    st.warning("Nenhum atendimento encontrado para Vinícius nesse período.")
    st.stop()

# opções
arred_cheio = st.checkbox("Arredondar p/ preço cheio", value=True)
tol_reais = st.number_input("Tolerância p/ arredondar (R$)", value=2.0, step=0.5)
pagar_caixinha = st.checkbox("Incluir Caixinha", value=True)

descricao_cx = "Caixinha Vinícius"
meio_pag_cx = "Dinheiro"

# =========================
# CALCULAR
# =========================
def montar_valor_base():
    linhas = []
    total_comissao = 0.0
    total_caixinha = 0.0

    # coluna numérica
    base_jan_vini["Valor_num"] = pd.to_numeric(base_jan_vini["Valor"], errors="coerce").fillna(0.0)

    for _, row in base_jan_vini.iterrows():
        data_serv = str(row["Data"]).strip()
        serv = str(row["Serviço"]).strip()
        bruto = float(row["Valor_num"])
        val_final = snap_para_preco_cheio(serv, bruto, tol_reais, arred_cheio)

        total_comissao += val_final
        linhas.append({
            "Data": data_serv,
            "Prestador": "Vinicius",
            "Descrição": f"Comissão Vinícius — Comp {data_fim.strftime('%m/%Y')} — Pago em {to_br_date(data_fim)}",
            "Valor": f"R$ {val_final:.2f}".replace(".", ","),
            "Me Pag:": "Dinheiro",
            "RefID": _refid_despesa(data_serv, "Vinicius", serv, val_final, "Dinheiro")
        })

    # Caixinha por dia
    linhas_caixinha = 0
    if pagar_caixinha:
        base_jan_vini["CaixinhaDia_num"] = pd.to_numeric(base_jan_vini.get("CaixinhaDia", 0), errors="coerce").fillna(0.0)
        base_jan_vini["CaixinhaFundo_num"] = pd.to_numeric(base_jan_vini.get("CaixinhaFundo", 0), errors="coerce").fillna(0.0)
        base_jan_vini["CaixinhaRow_num"] = pd.to_numeric(base_jan_vini.get("CaixinhaRow", 0), errors="coerce").fillna(0.0)

        base_cx = base_jan_vini.copy()
        base_cx["ValorCxTotal"] = (
            base_cx["CaixinhaDia_num"] + base_cx["CaixinhaFundo_num"] + base_cx["CaixinhaRow_num"]
        )
        cx_por_dia = base_cx.groupby("Data", dropna=False)["ValorCxTotal"].sum().reset_index()

        for _, row in cx_por_dia.iterrows():
            data_serv = str(row["Data"]).strip()
            valf = float(row["ValorCxTotal"])
            if valf <= 0:
                continue
            valor_txt = f'R$ {valf:.2f}'.replace(".", ",")
            desc_txt = f"{descricao_cx} — Pago em {to_br_date(data_fim)}"
            refid = _refid_despesa(data_serv, "Vinicius", desc_txt, valf, meio_pag_cx)
            linhas.append({
                "Data": data_serv,
                "Prestador": "Vinicius",
                "Descrição": desc_txt,
                "Valor": valor_txt,
                "Me Pag:": meio_pag_cx,
                "RefID": refid
            })
        total_caixinha = cx_por_dia["ValorCxTotal"].sum()
        linhas_caixinha = int((cx_por_dia["ValorCxTotal"] > 0).sum())

    return linhas, total_comissao, total_caixinha, linhas_caixinha

linhas, total_comissao, total_caixinha, linhas_caixinha = montar_valor_base()

st.write("### Resumo")
st.write(f"💈 Comissão de Vinícius: **R$ {total_comissao:.2f}**")
if pagar_caixinha:
    st.write(f"🎁 Caixinha: **R$ {total_caixinha:.2f}** ({linhas_caixinha} dias)")

# =========================
# BOTÕES
# =========================
if st.button("💾 Registrar no Despesas"):
    df_final = pd.concat([df_desp, pd.DataFrame(linhas)], ignore_index=True)
    salvar_df(ABA_DESPESAS, df_final)
    st.success("Registros gravados em Despesas.")
