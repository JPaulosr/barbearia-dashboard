def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        servico = build("drive", "v3", credentials=credenciais)

        # ID da pasta compartilhada correta
        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
        nome_arquivo = f"{nome_cliente}.jpg"

        # Define metadados do arquivo
        metadata = {
            "name": nome_arquivo,
            "parents": [pasta_id]
        }

        # Faz upload com suporte a pastas compartilhadas
        media = MediaFileUpload(caminho_arquivo, resumable=True)
        arquivo = servico.files().create(
            body=metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True  # 🚨 IMPORTANTE!
        ).execute()

        # Define permissão pública (para exibir no app)
        permissao = {"type": "anyone", "role": "reader"}
        servico.permissions().create(
            fileId=arquivo["id"],
            body=permissao,
            supportsAllDrives=True  # 🚨 IMPORTANTE!
        ).execute()

        return True, arquivo.get("id")
    except Exception as e:
        return False, str(e)
