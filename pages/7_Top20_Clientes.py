@st.cache_data
def carregar_dados(arquivo):
    df = pd.read_excel(arquivo)
    
    # Normaliza colunas
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mostra colunas disponíveis para depuração
    st.write("🧪 Colunas encontradas na planilha:", df.columns.tolist())

    # Mapeamento flexível
    mapa_colunas = {}
    for col in df.columns:
        col_n = unidecode(col.lower().strip())
        if "cliente" in col_n:
            mapa_colunas["Cliente"] = col
        elif "data" in col_n:
            mapa_colunas["Data"] = col
        elif "valor" in col_n:
            mapa_colunas["Valor"] = col

    # Verificação de colunas obrigatórias
    if not {"Cliente", "Data", "Valor"}.issubset(mapa_colunas.keys()):
        st.error("❌ A planilha deve conter colunas com os nomes (ou parecidos com): Cliente, Data e Valor.")
        return None

    # Renomeia colunas no DataFrame
    df = df.rename(columns={
        mapa_colunas["Cliente"]: "Cliente",
        mapa_colunas["Data"]: "Data",
        mapa_colunas["Valor"]: "Valor"
    })

    df = df.dropna(subset=["Cliente", "Data", "Valor"])
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Cliente_Normalizado"] = df["Cliente"].apply(lambda x: unidecode(str(x)).lower().strip())
    return df
