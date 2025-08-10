import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from gspread.utils import rowcol_to_a1

# ========= CONFIG =========
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

# ========= CONEXÃO =========
@st.cache_resource
def conectar():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def carregar_df(ws):
    df = get_as_dataframe(ws, evaluate_formulas=True).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    # garante colunas mínimas
    for c in ["Data","Cliente","Combo","Período"]:
        if c not in df.columns:
            df[c] = ""
    # normaliza período
    norm = {"manha":"Manhã","Manha":"Manhã","manha ":"Manhã","tarde":"Tarde","noite":"Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã","Tarde","Noite"]), "Período"] = ""
    return df

def col_index(headers, nome):
    try:
        return headers.index(nome) + 1
    except ValueError:
        return None

# ========= APP =========
st.set_page_config(page_title="Propagar Período em Combos", layout="wide")
st.title("🧹 Propagar Período nas linhas de Combo")

st.write("Isto vai copiar o **Período** da linha já preenchida para **todas** as linhas do mesmo **Combo (Data + Cliente + Combo)** que estiverem vazias.")

if st.button("🔍 Simular (não escreve)"):
    sh = conectar()
    ws = sh.worksheet(ABA_DADOS)
    df = carregar_df(ws)

    # somente combos
    is_combo = df["Combo"].astype(str).str.strip() != ""
    dfc = df[is_combo].copy()

    def modo_nao_vazio(s):
        vals = [v for v in s if isinstance(v, str) and v.strip() != ""]
        if not vals:
            return ""
        mode = pd.Series(vals).mode()
        return mode.iloc[0] if not mode.empty else vals[0]

    # valor de período por grupo
    grupos = dfc.groupby(["Data","Cliente","Combo"], dropna=False)["Período"].agg(modo_nao_vazio).reset_index()
    df_merge = pd.merge(dfc.reset_index(), grupos, on=["Data","Cliente","Combo"], how="left", suffixes=("","_grp"))

    # candidatos a preencher: período atual vazio e grupo com valor
    to_fill = (df_merge["Período"].astype(str).str.strip() == "") & (df_merge["Período_grp"].astype(str).str.strip() != "")
    qtd = int(to_fill.sum())

    st.info(f"Linhas de combo analisadas: {len(dfc)}")
    st.success(f"Preenchimentos necessários (simulação): {qtd}")

if st.button("✅ Executar (escrever no Google Sheets)"):
    with st.spinner("Processando..."):
        sh = conectar()
        ws = sh.worksheet(ABA_DADOS)
        df = carregar_df(ws)

        headers = list(df.columns)
        col_periodo = col_index(headers, "Período")
        if not col_periodo:
            st.error("Não encontrei a coluna 'Período' na planilha.")
            st.stop()

        # somente combos
        is_combo = df["Combo"].astype(str).str.strip() != ""
        idx_combo = df[is_combo].index

        def modo_nao_vazio(s):
            vals = [v for v in s if isinstance(v, str) and v.strip() != ""]
            if not vals:
                return ""
            mode = pd.Series(vals).mode()
            return mode.iloc[0] if not mode.empty else vals[0]

        grupos = df.loc[idx_combo].groupby(["Data","Cliente","Combo"], dropna=False)["Período"].agg(modo_nao_vazio).reset_index()

        # mapeia para cada linha combo o período do grupo
        dfc = df.loc[idx_combo].reset_index()
        dfc = pd.merge(dfc, grupos, on=["Data","Cliente","Combo"], how="left", suffixes=("","_grp"))

        # define novos valores
        preencher_mask = (dfc["Período"].astype(str).str.strip() == "") & (dfc["Período_grp"].astype(str).str.strip() != "")
        df.loc[dfc.loc[preencher_mask, "index"], "Período"] = dfc.loc[preencher_mask, "Período_grp"].values

        # prepara atualização apenas da coluna Período (linhas 2..N)
        valores = df["Período"].astype(str).tolist()
        rng = f"{rowcol_to_a1(2, col_periodo)}:{rowcol_to_a1(len(valores)+1, col_periodo)}"
        payload = [[v] for v in valores]
        ws.update(rng, payload, value_input_option="USER_ENTERED")

        st.success(f"Concluído! Linhas atualizadas: {int(preencher_mask.sum())}")
        st.caption("Obs.: apenas a coluna 'Período' foi escrita; demais colunas permaneceram intactas.")
