def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        servico = build("drive", "v3", credentials=credenciais)

        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
        nome_arquivo = f"{nome_cliente}.jpg"

        # 🔄 Verifica se já existe arquivo com o mesmo nome
        resultado = servico.files().list(
            q=f"'{pasta_id}' in parents and name='{nome_arquivo}' and trashed=false",
            fields="files(id, name)"
        ).execute()
        arquivos = resultado.get("files", [])

        # 🧹 Se já existir, remove antes de reenviar
        for arq in arquivos:
            servico.files().delete(fileId=arq["id"]).execute()

        # 📤 Faz upload
        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaFileUpload(caminho_arquivo, resumable=True)
        arquivo = servico.files().create(body=metadata, media_body=media, fields="id").execute()

        # 🌍 Permissão de leitura pública
        permissao = {"type": "anyone", "role": "reader"}
        servico.permissions().create(fileId=arquivo["id"], body=permissao).execute()

        return True, arquivo.get("id")

    except Exception as e:
        return False, str(e)
