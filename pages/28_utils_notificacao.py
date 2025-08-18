import time

@st.cache_data(ttl=300, show_spinner=False)
def carregar_base_seguro():
    t0 = time.perf_counter()
    try:
        sh = conectar_sheets()       # cache_resource: conexão
        ws = sh.worksheet(ABA_DADOS)

        # 1) Tenta caminho rápido: get_all_records (mais estável que get_as_dataframe em alguns ambientes)
        #    numericise_ignore evita conversões agressivas que quebram datas em PT-BR
        records = ws.get_all_records(numericise_ignore=['all'])
        df = pd.DataFrame(records)

        # 2) Se vier vazio, tenta gspread_dataframe (mantém compatibilidade com sua estrutura)
        if df.empty:
            df = get_as_dataframe(ws).dropna(how="all")

        df.columns = [str(col).strip() for col in df.columns]
        # Garante colunas oficiais e fiado
        for coluna in [*COLS_OFICIAIS, *COLS_FIADO]:
            if coluna not in df.columns:
                df[coluna] = ""

        # Normaliza Período
        norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
        df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
        df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""

        df["Combo"] = df["Combo"].fillna("")

        st.session_state["_LOAD_MS"] = int((time.perf_counter() - t0) * 1000)
        return df, ws

    except Exception as e:
        # Mostra erro no app (sem travar) e repropaga
        st.error(f"❌ Falha ao carregar a planilha: {e}")
        raise

def carregar_base():
    # Encapsula para manter o seu nome original
    return carregar_base_seguro()
