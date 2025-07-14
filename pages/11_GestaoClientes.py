import cloudinary
import cloudinary.uploader

# Configuração (você pode guardar isso no st.secrets se preferir)
cloudinary.config(
    cloud_name='SEU_CLOUD_NAME',
    api_key='SUA_API_KEY',
    api_secret='SEU_API_SECRET'
)

# Caminho local da imagem que você acabou de gerar
caminho_imagem = "A_logo_for_\"Salão_JP\"_is_displayed_against_a_dark_.png"

# Upload
resposta = cloudinary.uploader.upload(caminho_imagem, folder="Fotos clientes", public_id="logo_padrao_salaoJP")
print("URL da imagem:", resposta["secure_url"])
