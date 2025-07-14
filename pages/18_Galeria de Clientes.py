import gspread
from google.oauth2.service_account import Credentials
import streamlit as st

def remover_linhas_com_nome_vazio():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"], scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"])
        aba = planilha.worksheet("clientes_status")

        dados = aba.get_all_values()
        header = dados[0]
        linhas = dados[1:]

        idx_cliente = header.index("Cliente")
        st.write(f"🔍 Coluna 'Cliente' localizada na posição {idx_cliente + 1}")

        linhas_para_excluir = []
        for i, linha in enumerate(linhas, start=2):  # linha 2 = primeira linha de dados
            nome = linha[idx_cliente].strip() if len(linha) > idx_cliente else ""
            if nome == "":
                st.warning(f"⛔ Linha {i} marcada para exclusão (cliente vazio): {linha}")
                linhas_para_excluir.append(i)

        if not linhas_para_excluir:
            st.success("✅ Nenhuma linha com nome vazio encontrada.")
            return

        for linha_index in reversed(linhas_para_excluir):
            aba.delete_rows(linha_index)
            st.info(f"🗑️ Linha {linha_index} removida com sucesso.")

        st.success(f"✅ {len(linhas_para_excluir)} linha(s) foram removidas da planilha.")

    except Exception as e:
        st.error(f"❌ Erro ao remover linhas: {e}")
