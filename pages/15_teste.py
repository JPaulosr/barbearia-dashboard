@st.cache_data(show_spinner=False)
def carregar_lista_clientes():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])

        # Nome da aba correta que contém a lista de clientes
        aba = planilha.worksheet("clientes_status")

        # Evitar erro se estiver vazia
        valores = aba.get_all_values()
        if len(valores) <= 1:
            st.warning("A aba 'clientes_status' está vazia ou sem dados.")
            return pd.DataFrame(columns=["Cliente", "Status"])

        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        return df

    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return pd.DataFrame(columns=["Cliente", "Status"])
