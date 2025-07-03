import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

st.set_page_config(page_title="Upload de Imagem do Cliente", layout="wide")
st.markdown("## 📸 Upload de Imagem do Cliente")

# Função para carregar a lista de clientes
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
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        return sorted(df["Cliente"].dropna().unique())
    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return []

# Função para fazer upload da imagem e torná-la pública
def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        servico = build("drive", "v3", credentials=credenciais)

        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
        nome_arquivo = f"{nome_cliente}.jpg"

        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaFileUpload(caminho_arquivo, resumable=True)

        arquivo = servico.files().create(
            body=metadata,
            media_body=media,
            fields="id, name"
        ).execute()

        file_id = arquivo.get("id")
        file_name = arquivo.get("name")

        if not file_id:
            return False, "ID do arquivo não retornado pelo Drive."

        # Torna o arquivo público
        permissao = {"type": "anyone", "role": "reader"}
        servico.permissions().create(fileId=file_id, body=permissao).execute()

        print(f"✅ Imagem '{file_name}' enviada com ID: {file_id}")
        return True, file_id

    except Exception as e:
        return False, str(e)

# Interface
clientes = carregar_lista_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente:", clientes)

# Mostrar imagem existente
if cliente_selecionado:
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()

        for linha in dados:
            if linha.get("Cliente") == cliente_selecionado:
                link_foto = linha.get("Foto")
                if link_foto:
                    st.image(link_foto, caption=f"Foto de {cliente_selecionado}", use_container_width=False)
                else:
                    st.info("Nenhuma imagem cadastrada para este cliente.")
                break
    except Exception as e:
        st.warning(f"Erro ao buscar imagem: {e}")

# Upload de nova imagem
arquivo = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

if st.button("💾 Enviar imagem"):
    if cliente_selecionado and arquivo:
        try:
            caminho_temp = f"temp_{cliente_selecionado}.jpg"
            with open(caminho_temp, "wb") as f:
                f.write(arquivo.read())

            sucesso, resposta = upload_imagem_drive(caminho_temp, cliente_selecionado)
            os.remove(caminho_temp)

            # 🔍 DEBUG
            st.markdown("### 🔍 DEBUG")
            st.write(f"- Sucesso no upload: {sucesso}")
            st.write(f"- ID retornado do Drive: {resposta}")
            st.write(f"- URL montada: https://drive.google.com/uc?export=download&id={resposta}")

            if sucesso:
                try:
                    # ✅ LINK FINAL COMPATÍVEL COM STREAMLIT
                    link_imagem = f"https://drive.google.com/uc?export=download&id={resposta}"

                    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                    credenciais = Credentials.from_service_account_info(
                        st.secrets["GCP_SERVICE_ACCOUNT"],
                        scopes=escopos
                    )
                    cliente = gspread.authorize(credenciais)
                    planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
                    aba = planilha.worksheet("clientes_status")

                    dados = aba.get_all_records()
                    cabecalho = aba.row_values(1)
                    coluna_foto = None

                    for i, nome_coluna in enumerate(cabecalho):
                        if nome_coluna.strip().lower() == "foto":
                            coluna_foto = i + 1
                            break

                    if not coluna_foto:
                        coluna_foto = len(cabecalho) + 1
                        aba.update_cell(1, coluna_foto, "Foto")

                    for idx, linha in enumerate(dados, start=2):
                        if linha.get("Cliente") == cliente_selecionado:
                            aba.update_cell(idx, coluna_foto, link_imagem)
                            break

                    st.success("✅ Imagem enviada e link registrado com sucesso!")
                except Exception as e:
                    st.warning(f"Imagem enviada, mas falha ao atualizar a planilha: {e}")
            else:
                st.error(f"Erro no upload: {resposta}")

        except Exception as erro:
            st.error(f"Erro inesperado: {erro}")
    else:
        st.warning("Selecione um cliente e uma imagem antes de enviar.")
