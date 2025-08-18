import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import requests
import textwrap

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

# Colunas “oficiais” e colunas de FIADO que devemos preservar
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]  # incluo DataPagamento p/ competência

# === VALORES PADRÃO DE SERVIÇO ===
valores_servicos = {
    "Corte": 25.0,
    "Pezinho": 7.0,
    "Barba": 15.0,
    "Sobrancelha": 7.0,
    "Luzes": 45.0,
    "Pintura": 35.0,
    "Alisamento": 40.0,
    "Gel": 10.0,
    "Pomada": 15.0,
}

LOGO_PADRAO = st.secrets.get("LOGO_PADRAO", "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png")

# ====== CONEXÃO ======
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def ler_cabecalho(aba):
    try:
        headers = aba.row_values(1)
        headers = [h.strip() for h in headers] if headers else []
        return headers
    except Exception:
        return []

@st.cache_data(ttl=120)
def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]

    # >>> Garante colunas oficiais e de fiado (sem remover as que já existem)
    for coluna in [*COLS_OFICIAIS, *COLS_FIADO]:
        if coluna not in df.columns:
            df[coluna] = ""

    # Normaliza Período
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    if "Período" in df.columns:
        df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
        df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""

    if "Combo" in df.columns:
        df["Combo"] = df["Combo"].fillna("")

    return df, aba

def salvar_base(df_final):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = ler_cabecalho(aba)

    # Se a planilha estiver vazia (sem cabeçalho), cria um com oficiais + fiado
    if not headers_existentes:
        headers_existentes = [*COLS_OFICIAIS, *COLS_FIADO]

    # Garante todas as colunas do cabeçalho + oficiais + fiado
    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_FIADO]))
    for col in colunas_alvo:
        if col not in df_final.columns:
            df_final[col] = ""

    # Reordena pelas colunas alvo (preserva as extras que já existiam)
    df_final = df_final[colunas_alvo]

    # Escreve
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

def obter_valor_servico(servico):
    for chave in valores_servicos.keys():
        if chave.lower() == servico.lower():
            return float(valores_servicos[chave])
    return 0.0

def ja_existe_atendimento(cliente, data, servico, combo=""):
    df, _ = carregar_base()
    df["Combo"] = df["Combo"].fillna("")
    existe = df[
        (df["Cliente"] == cliente) &
        (df["Data"] == data) &
        (df["Serviço"] == servico) &
        (df["Combo"] == combo)
    ]
    return not existe.empty

def _preencher_fiado_vazio(linha: dict):
    for c in COLS_FIADO:
        linha.setdefault(c, "")
    return linha

# ====== INSTAGRAM ======
def _baixar_logo(url: str) -> Image.Image:
    try:
        r = requests.get(url, timeout=6)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception:
        # fallback: logo vazio
        img = Image.new("RGBA", (1,1), (0,0,0,0))
        return img

def gerar_card_instagram(cliente, data_br, servicos, funcionario, valor_total):
    # Canvas
    W, H = 1080, 1350  # retrato para feed (1:1.25) / também serve para story (recorta)
    bg = Image.new("RGB", (W, H), (15, 15, 15))
    draw = ImageDraw.Draw(bg)

    # Logo
    logo = _baixar_logo(LOGO_PADRAO)
    if logo.width > 0:
        # encaixa no topo
        target_w = 180
        ratio = target_w / max(1, logo.width)
        logo = logo.resize((int(logo.width*ratio), int(logo.height*ratio)))
        bg.paste(logo, (60, 60), logo)

    # fontes
    try:
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 72)
        font_sub = ImageFont.truetype("DejaVuSans.ttf", 42)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 32)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Títulos
    y = 60 + (logo.height if logo.width > 0 else 0) + 50
    draw.text((60, y), "Novo atendimento 💈", fill=(255,255,255), font=font_title)
    y += 90
    draw.text((60, y), f"Cliente: {cliente}", fill=(220,220,220), font=font_sub)
    y += 60
    draw.text((60, y), f"Data: {data_br}", fill=(220,220,220), font=font_sub)
    y += 60
    draw.text((60, y), f"Atendido por: {funcionario}", fill=(220,220,220), font=font_sub)
    y += 80

    # Lista de serviços (quebra em linhas)
    draw.text((60, y), "Serviços:", fill=(255,255,255), font=font_sub)
    y += 58
    wrap_width = 28
    for s in servicos:
        for line in textwrap.wrap(f"• {s}", width=wrap_width):
            draw.text((90, y), line, fill=(200,200,200), font=font_small)
            y += 44
    y += 20

    # Valor total (opcional)
    if valor_total is not None:
        draw.text((60, y), f"Total: R$ {valor_total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."), fill=(255,255,255), font=font_sub)

    # rodapé
    footer = "Siga @seu_salao • Agende seu horário ✂️"
    draw.text((60, H-80), footer, fill=(160,160,160), font=font_small)

    # buffer
    buf = BytesIO()
    bg.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def tentar_postar_instagram(png_bytes: BytesIO, legenda: str):
    """
    Posta via Instagram Graph API (somente conta Business).
    Requer secrets:
      - INSTAGRAM_IG_USER_ID
      - INSTAGRAM_TOKEN (long-lived)
    """
    ig_user_id = st.secrets.get("INSTAGRAM_IG_USER_ID")
    token = st.secrets.get("INSTAGRAM_TOKEN")
    if not ig_user_id or not token:
        return False, "Credenciais do Instagram não configuradas (usando download manual)."

    # 1) criar container (upload da imagem por URL é mais simples; aqui vamos subir como multipart para um host temporário)
    # Como simplificação, vamos converter para base64 + usar upload anônimo do imgbb se você fornecer IMG_BB_KEY em secrets.
    imgbb_key = st.secrets.get("IMG_BB_KEY")
    if not imgbb_key:
        return False, "IMG_BB_KEY ausente nos secrets (sem URL pública da imagem). Gerado card para download."

    try:
        # sobe imagem para imgbb
        b64 = st.base64.b64encode(png_bytes.getvalue()).decode("utf-8")
    except Exception:
        import base64
        b64 = base64.b64encode(png_bytes.getvalue()).decode("utf-8")

    try:
        r_up = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": imgbb_key, "image": b64},
            timeout=15
        )
        r_up.raise_for_status()
        image_url = r_up.json()["data"]["url"]
    except Exception as e:
        return False, f"Falha ao hospedar imagem (imgbb): {e}"

    try:
        # 1) create container
        create = requests.post(
            f"https://graph.facebook.com/v20.0/{ig_user_id}/media",
            data={
                "image_url": image_url,
                "caption": legenda,
                "access_token": token
            },
            timeout=15
        )
        create.raise_for_status()
        container_id = create.json()["id"]

        # 2) publish
        publish = requests.post(
            f"https://graph.facebook.com/v20.0/{ig_user_id}/media_publish",
            data={"creation_id": container_id, "access_token": token},
            timeout=15
        )
        publish.raise_for_status()
        return True, "Post publicado no Instagram com sucesso."
    except Exception as e:
        return False, f"Falha ao publicar no Instagram: {e}"

# ====== UI ======
st.title("📅 Adicionar Atendimento")

df_existente, _ = carregar_base()
# Preparar listas
df_existente["Data"] = pd.to_datetime(df_existente["Data"], format="%d/%m/%Y", errors="coerce")
df_2025 = df_existente[df_existente["Data"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025 = df_2025[df_2025["Serviço"].notna()].copy()
servicos_existentes = sorted(df_2025["Serviço"].astype(str).str.strip().unique())
contas_existentes = sorted(df_2025["Conta"].dropna().astype(str).unique())
combos_existentes = sorted(df_2025["Combo"].dropna().astype(str).unique())

# === SELEÇÃO E AUTOPREENCHIMENTO ===
col1, col2 = st.columns(2)

with col1:
    data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")
    cliente = st.selectbox("Nome do Cliente", clientes_existentes)
    novo_nome = st.text_input("Ou digite um novo nome de cliente")
    cliente = novo_nome if novo_nome else cliente

    ultimo = df_existente[df_existente["Cliente"] == cliente]
    ultimo = ultimo.sort_values("Data", ascending=False).iloc[0] if not ultimo.empty else None
    conta_sugerida = (ultimo["Conta"] if ultimo is not None else "") or ""
    funcionario_sugerido = (ultimo["Funcionário"] if ultimo is not None else "JPaulo") or "JPaulo"
    combo_sugerido = (ultimo["Combo"] if (ultimo is not None and ultimo["Combo"]) else "") or ""

    conta = st.selectbox("Forma de Pagamento", list(dict.fromkeys([conta_sugerida] + contas_existentes + ["Carteira", "Nubank"])))
    combo = st.selectbox("Combo (opcional - use 'corte+barba')", [""] + list(dict.fromkeys([combo_sugerido] + combos_existentes)))

with col2:
    funcionario = st.selectbox(
        "Funcionário", ["JPaulo", "Vinicius"],
        index=["JPaulo", "Vinicius"].index(funcionario_sugerido) if funcionario_sugerido in ["JPaulo", "Vinicius"] else 0
    )
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])

fase = "Dono + funcionário"
periodo_opcao = st.selectbox("Período do Atendimento", ["Manhã", "Tarde", "Noite"])

# === CONTROLE DE ESTADO ===
if "combo_salvo" not in st.session_state:
    st.session_state.combo_salvo = False
if "simples_salvo" not in st.session_state:
    st.session_state.simples_salvo = False

if st.button("🧹 Limpar formulário"):
    st.session_state.combo_salvo = False
    st.session_state.simples_salvo = False
    st.rerun()

# ===== SALVAMENTO =====
def salvar_linhas(linhas: list):
    df, _ = carregar_base()
    novas = []
    for lin in linhas:
        novas.append(_preencher_fiado_vazio(lin))
    df_final = pd.concat([df, pd.DataFrame(novas)], ignore_index=True)
    salvar_base(df_final)

def salvar_combo(combo_str, valores_customizados):
    servicos = [s.strip() for s in combo_str.split("+") if s.strip()]
    linhas = []
    for servico_formatado in servicos:
        valor = float(valores_customizados.get(servico_formatado, obter_valor_servico(servico_formatado)))
        linhas.append({
            "Data": data,
            "Serviço": servico_formatado,
            "Valor": valor,
            "Conta": conta,
            "Cliente": cliente,
            "Combo": combo_str,
            "Funcionário": funcionario,
            "Fase": fase,
            "Tipo": tipo,
            "Período": periodo_opcao,
        })
    salvar_linhas(linhas)
    return servicos, sum(float(x["Valor"]) for x in linhas)

def salvar_multiplos_servicos(servicos_escolhidos, valores_por_servico):
    linhas = []
    for s in servicos_escolhidos:
        valor = float(valores_por_servico.get(s, obter_valor_servico(s)))
        linhas.append({
            "Data": data, "Serviço": s, "Valor": valor, "Conta": conta, "Cliente": cliente,
            "Combo": "", "Funcionário": funcionario, "Fase": fase, "Tipo": tipo, "Período": periodo_opcao
        })
    salvar_linhas(linhas)
    return servicos_escolhidos, sum(float(x["Valor"]) for x in linhas)

# ===== FORMULÁRIO =====
if combo:
    st.subheader("💰 Edite os valores do combo antes de salvar:")
    valores_customizados = {}
    for servico in [s.strip() for s in combo.split("+") if s.strip()]:
        valor_padrao = obter_valor_servico(servico)
        valor = st.number_input(
            f"{servico} (padrão: R$ {valor_padrao})",
            value=float(valor_padrao), step=1.0, key=f"valor_combo_{servico}"
        )
        valores_customizados[servico] = valor

    if not st.session_state.combo_salvo:
        if st.button("✅ Confirmar e Salvar Combo"):
            duplicado = any(ja_existe_atendimento(cliente, data, s.strip(), combo) for s in combo.split("+"))
            if duplicado:
                st.warning("⚠️ Combo já registrado para este cliente e data.")
            else:
                servicos_salvos, total = salvar_combo(combo, valores_customizados)
                st.session_state.combo_salvo = True
                st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
                # Instagram se for Vinicius
                if funcionario == "Vinicius":
                    legenda = f"Novo atendimento de {cliente} em {data} • Serviços: {', '.join(servicos_salvos)}"
                    buf_png = gerar_card_instagram(cliente, data, servicos_salvos, funcionario, total)
                    st.image(buf_png, caption="Prévia do card para Instagram", use_container_width=True)
                    ok, msg = tentar_postar_instagram(buf_png, legenda)
                    st.info(msg)
                    st.download_button("⬇️ Baixar card (PNG)", data=buf_png, file_name=f"card_{cliente}_{data}.png", mime="image/png")
    else:
        if st.button("➕ Novo Atendimento"):
            st.session_state.combo_salvo = False
            st.rerun()

else:
    st.subheader("✂️ Selecione os serviços e valores (vários de uma vez):")
    # Multiseleção de serviços
    escolhas = st.multiselect("Serviços", options=sorted(valores_servicos.keys()))
    valores_por_servico = {}
    for s in escolhas:
        valor_padrao = obter_valor_servico(s)
        valores_por_servico[s] = st.number_input(
            f"{s} (padrão: R$ {valor_padrao})",
            value=float(valor_padrao), step=1.0, key=f"valor_multi_{s}"
        )

    if not st.session_state.simples_salvo:
        if st.button("📁 Salvar Atendimento(s)"):
            if not escolhas:
                st.warning("Selecione pelo menos um serviço.")
            else:
                # duplicidade: se algum serviço já existir na mesma data/cliente
                dups = [s for s in escolhas if ja_existe_atendimento(cliente, data, s)]
                if dups:
                    st.warning("⚠️ Já existe(m) para este cliente e data: " + ", ".join(dups))
                # salva mesmo que alguns já existam? Mantive bloqueio parcial: salva só os não duplicados
                escolhas_para_salvar = [s for s in escolhas if s not in dups]
                if escolhas_para_salvar:
                    servicos_salvos, total = salvar_multiplos_servicos(escolhas_para_salvar, valores_por_servico)
                    st.session_state.simples_salvo = True
                    st.success(f"✅ Atendimento salvo para {cliente} no dia {data}.")
                    if funcionario == "Vinicius":
                        legenda = f"Novo atendimento de {cliente} em {data} • Serviços: {', '.join(servicos_salvos)}"
                        buf_png = gerar_card_instagram(cliente, data, servicos_salvos, funcionario, total)
                        st.image(buf_png, caption="Prévia do card para Instagram", use_container_width=True)
                        ok, msg = tentar_postar_instagram(buf_png, legenda)
                        st.info(msg)
                        st.download_button("⬇️ Baixar card (PNG)", data=buf_png, file_name=f"card_{cliente}_{data}.png", mime="image/png")
                else:
                    st.stop()
    else:
        if st.button("➕ Novo Atendimento"):
            st.session_state.simples_salvo = False
            st.rerun()
