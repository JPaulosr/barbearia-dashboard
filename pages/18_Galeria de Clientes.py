import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Limpeza de Clientes", layout="wide")
st.title("🧹 Limpeza de Clientes com nome em branco")

# ========== TESTE DE LEITURA DA PLANILHA ==========
try:
    escopos = ["https://www.googleapis.com/auth/spreadsheets"]
    credenciais = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"], scopes=escopos
    )
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"])
    aba = planilha.worksheet("clientes_status")
    dados = aba.get_all_values()
    st.success("✅ Leitura da planilha bem-sucedida.")
    st.dataframe(dados[:10])  # Visualiza os primeiros 10 registros
except Exception as e:
    st.error(f"❌ Erro ao ler a planilha: {e}")
    st.stop()

# ========== FUNÇÃO DE LIMPEZA ==========
def remover_linhas_com_nome_vazio():
    try:
        header = dados[0]
        linhas = dados[1:]

        idx_cliente = header.index("Cliente")
        st.write(f"📌 Coluna 'Cliente' está na posição {idx_cliente + 1}.")

        linhas_para_excluir = []
        for i, linha in enumerate(linhas, start=2):  # linha 2 = primeira linha de dados
            nome = linha[idx_cliente].strip() if len(linha) > idx_cliente else ""
            if nome == "":
                st.warning(f"⛔ Linha {i} marcada para exclusão: {linha}")
                linhas_para_excluir.append(i)

        if not linhas_para_excluir:
            st.success("✅ Nenhuma linha com nome vazio encontrada.")
            return

        for linha_index in reversed(linhas_para_excluir):
            aba.delete_rows(linha_index)
            st.info(f"🗑️ Linha {linha_index} removida.")

        st.success(f"✅ {len(linhas_para_excluir)} linha(s) foram removidas com sucesso.")

    except Exception as e:
        st.error(f"❌ Erro ao remover linhas: {e}")

# ========== BOTÃO PARA EXECUTAR A LIMPEZA ==========
if st.button("🧽 Remover clientes com nome em branco"):
    st.write("🔁 Botão foi clicado!")
    remover_linhas_com_nome_vazio()
