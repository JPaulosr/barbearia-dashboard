import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import datetime
import pytz
import json
import unicodedata
import requests

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
STATUS_ABA = "clientes_status"  # onde está Cliente + link da foto
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

TZ = "America/Sao_Paulo"
REL_MULT = 1.5  # classificação relativa: pouco = <= média*1.5, muito acima disso

# Colunas “oficiais” e FIADO
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]

# ----------------- Utils -----------------
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def classificar_relative(dias, media):
    if media is None:
        return ("⚪ Sem média", "Sem média")
    if dias <= media:
        return ("🟢 Em dia", "Em dia")
    elif dias <= media * REL_MULT:
        return ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        return ("🔴 Muito atrasado", "Muito atrasado")

def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

# -------------- Conexão Sheets -----------
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]

    # garante oficiais + fiado
    for coluna in [*COLS_OFICIAIS, *COLS_FIADO]:
        if coluna not in df.columns:
            df[coluna] = ""

    # normaliza Período
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""

    df["Combo"] = df["Combo"].fillna("")
    return df, aba

def salvar_base(df_final):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = ler_cabecalho(aba)
    if not headers_existentes:
        headers_existentes = [*COLS_OFICIAIS, *COLS_FIADO]

    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_FIADO]))
    for col in colunas_alvo:
        if col not in df_final.columns:
            df_final[col] = ""

    df_final = df_final[colunas_alvo]
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

# ---------- Fotos por cliente (status sheet) ----------
@st.cache_data(show_spinner=False)
def carregar_fotos_mapa():
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        # acha colunas
        cols_lower = {c.lower(): c for c in df.columns}
        foto_col = next((cols_lower[c] for c in FOTO_COL_CANDIDATES if c in cols_lower), None)
        cli_col = next((cols_lower[c] for c in ["cliente", "nome", "nome_cliente"] if c in cols_lower), None)
        if not (foto_col and cli_col):
            return {}
        tmp = df[[cli_col, foto_col]].copy()
        tmp.columns = ["Cliente", "Foto"]
        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
        return {r["k"]: str(r["Foto"]).strip() for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
    except Exception:
        return {}

FOTOS = carregar_fotos_mapa()

# --------- Telegram ----------
def _has_telegram():
    return ("TELEGRAM_TOKEN" in st.secrets) and ("TELEGRAM_CHAT_ID" in st.secrets)

def tg_send(text):
    if not _has_telegram():
        return
    try:
        url = f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendMessage"
        payload = {"chat_id": st.secrets["TELEGRAM_CHAT_ID"], "text": text,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        st.warning(f"Falha ao enviar Telegram: {e}")

def tg_send_photo(photo_url, caption):
    if not _has_telegram():
        return
    try:
        url = f"https://api.telegram.org/bot{st.secrets['TELEGRAM_TOKEN']}/sendPhoto"
        payload = {"chat_id": st.secrets["TELEGRAM_CHAT_ID"], "photo": photo_url,
                   "caption": caption, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=30)
    except Exception as e:
        st.warning(f"Falha ao enviar foto (Telegram): {e}")
        tg_send(caption)

def make_card_caption(nome, status_label, ultima_dt, media, dias_desde_ultima):
    ultima_str = pd.to_datetime(ultima_dt).strftime("%d/%m/%Y") if pd.notnull(ultima_dt) else "-"
    media_str = "-" if media is None else f"{media:.1f}".replace(".", ",")
    dias_str = "-" if dias_desde_ultima is None else str(int(dias_desde_ultima))
    emoji = {"Em dia":"🟢", "Pouco atrasado":"🟠", "Muito atrasado":"🔴"}.get(status_label, "")
    return (
        "📌 <b>Atendimento registrado</b>\n"
        f"👤 Cliente: <b>{nome}</b>\n"
        f"{emoji} Status: <b>{status_label}</b>\n"
        f"🗓️ Data: <b>{ultima_str}</b>\n"
        f"🔁 Média: <b>{media_str} dias</b>\n"
        f"⏳ Distância da última: <b>{dias_str} dias</b>"
    )

def calcular_metricas_cliente(df_all, cliente):
    # usa 1 visita por dia para média de intervalo
    d = df_all[df_all["Cliente"].astype(str).str.strip() == cliente].copy()
    if d.empty:
        return None, None, "Sem média"
    # parse datas
    d["_dt"] = pd.to_datetime(d["Data"], format="%d/%m/%Y", errors="coerce")
    d = d.dropna(subset=["_dt"])
    if d.empty:
        return None, None, "Sem média"
    dias_unicos = sorted(set(pd.to_datetime(d["_dt"]).dt.date.tolist()))
    ultima = pd.to_datetime(dias_unicos[-1])
    hoje = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)
    dias_since = (hoje - ultima).days
    media = None
    if len(dias_unicos) >= 2:
        dias_ts = [pd.to_datetime(x) for x in dias_unicos]
        diffs = [(dias_ts[i] - dias_ts[i-1]).days for i in range(1, len(dias_ts))]
        diffs_pos = [x for x in diffs if x > 0]
        if diffs_pos:
            media = sum(diffs_pos)/len(diffs_pos)
    _, status_label = classificar_relative(dias_since, media)
    return ultima, media, status_label

def enviar_card_vinicuis(df_all, cliente):
    ultima, media, status_label = calcular_metricas_cliente(df_all, cliente)
    caption = make_card_caption(cliente, status_label, ultima, media, (None if ultima is None else (pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None) - ultima).days))
    foto = FOTOS.get(_norm(cliente))
    if foto:
        tg_send_photo(foto, caption)
    else:
        tg_send(caption)

# -------- Valores padrão de serviço --------
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

def obter_valor_servico(servico):
    for chave in valores_servicos.keys():
        if chave.lower() == servico.lower():
            return valores_servicos[chave]
    return 0.0

def _preencher_fiado_vazio(linha: dict):
    for c in COLS_FIADO:
        linha.setdefault(c, "")
    return linha

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

# ------------------- UI -------------------
st.title("📅 Adicionar Atendimento")

df_existente, _ = carregar_base()
# parse para listas sugestivas
df_existente["_dt"] = pd.to_datetime(df_existente["Data"], format="%d/%m/%Y", errors="coerce")
df_2025 = df_existente[df_existente["_dt"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025 = df_2025[df_2025["Serviço"].notna()].copy()
servicos_existentes = sorted(df_2025["Serviço"].str.strip().unique())
contas_existentes = sorted(df_2025["Conta"].dropna().unique())
combos_existentes = sorted(df_2025["Combo"].dropna().unique())

# ------------ Toggle modo --------------
modo_lote = st.toggle("📦 Cadastro em Lote (vários clientes de uma vez)", value=False)

# campos comuns
col1, col2 = st.columns(2)
with col1:
    data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")
    conta = st.selectbox("Forma de Pagamento", list(dict.fromkeys(contas_existentes + ["Carteira", "Nubank"])))
    combo = st.selectbox("Combo (opcional - use 'corte+barba')", [""] + combos_existentes)
with col2:
    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"])
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
fase = "Dono + funcionário"
periodo_opcao = st.selectbox("Período do Atendimento", ["Manhã", "Tarde", "Noite"])

if not modo_lote:
    # ----------- MODO UM POR VEZ -----------
    colA, colB = st.columns(2)
    with colA:
        cliente = st.selectbox("Nome do Cliente", clientes_existentes)
    with colB:
        novo_nome = st.text_input("Ou digite um novo nome de cliente")
    cliente = novo_nome if novo_nome else cliente

    # sugestão últimos
    ultimo = df_existente[df_existente["Cliente"] == cliente]
    ultimo = ultimo.sort_values("Data", ascending=False).iloc[0] if not ultimo.empty else None
    if ultimo is not None:
        conta = st.selectbox("Forma de Pagamento (última primeiro)", list(dict.fromkeys([ultimo["Conta"]] + [conta] + contas_existentes)), index=0)
        combo = st.selectbox("Combo (último primeiro)", [""] + list(dict.fromkeys([ultimo["Combo"]] + [combo] + combos_existentes)))

    # controles
    if "combo_salvo" not in st.session_state:
        st.session_state.combo_salvo = False
    if "simples_salvo" not in st.session_state:
        st.session_state.simples_salvo = False
    if st.button("🧹 Limpar formulário"):
        st.session_state.combo_salvo = False
        st.session_state.simples_salvo = False
        st.rerun()

    # salvar
    if combo:
        st.subheader("💰 Edite os valores do combo antes de salvar:")
        valores_customizados = {}
        for servico in combo.split("+"):
            servico_formatado = servico.strip()
            valor_padrao = obter_valor_servico(servico_formatado)
            valor = st.number_input(f"{servico_formatado} (padrão: R$ {valor_padrao})",
                                    value=valor_padrao, step=1.0, key=f"valor_{servico_formatado}")
            valores_customizados[servico_formatado] = valor

        if not st.session_state.combo_salvo:
            if st.button("✅ Confirmar e Salvar Combo"):
                duplicado = any(ja_existe_atendimento(cliente, data, s.strip(), combo) for s in combo.split("+"))
                if duplicado:
                    st.warning("⚠️ Combo já registrado para este cliente e data.")
                else:
                    # salva
                    df_all, _ = carregar_base()
                    servicos = combo.split("+")
                    novas = []
                    for s in servicos:
                        s2 = s.strip()
                        linha = {
                            "Data": data, "Serviço": s2,
                            "Valor": valores_customizados.get(s2, obter_valor_servico(s2)),
                            "Conta": conta, "Cliente": cliente, "Combo": combo,
                            "Funcionário": funcionario, "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                        }
                        novas.append(_preencher_fiado_vazio(linha))
                    df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                    salvar_base(df_final)
                    st.session_state.combo_salvo = True
                    st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
                    if funcionario == "Vinicius":
                        enviar_card_vinicuis(df_final, cliente)
        else:
            if st.button("➕ Novo Atendimento"):
                st.session_state.combo_salvo = False
                st.rerun()
    else:
        st.subheader("✂️ Selecione o serviço e valor:")
        servico = st.selectbox("Serviço", servicos_existentes)
        valor_sugerido = obter_valor_servico(servico)
        valor = st.number_input("Valor", value=valor_sugerido, step=1.0)

        if not st.session_state.simples_salvo:
            if st.button("📁 Salvar Atendimento"):
                if ja_existe_atendimento(cliente, data, servico):
                    st.warning("⚠️ Atendimento já registrado para este cliente, data e serviço.")
                else:
                    df_all, _ = carregar_base()
                    nova = {
                        "Data": data, "Serviço": servico, "Valor": valor, "Conta": conta,
                        "Cliente": cliente, "Combo": "", "Funcionário": funcionario,
                        "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                    }
                    df_final = pd.concat([df_all, pd.DataFrame([_preencher_fiado_vazio(nova)])], ignore_index=True)
                    salvar_base(df_final)
                    st.session_state.simples_salvo = True
                    st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
                    if funcionario == "Vinicius":
                        enviar_card_vinicuis(df_final, cliente)
        else:
            if st.button("➕ Novo Atendimento"):
                st.session_state.simples_salvo = False
                st.rerun()

else:
    # ----------- MODO LOTE -----------
    st.info("Selecione vários clientes e salve todos de uma vez. O mesmo serviço/combo e dados serão aplicados.")
    clientes_multi = st.multiselect("Clientes existentes", clientes_existentes)
    novos_nomes_raw = st.text_area("Ou cole novos nomes (um por linha)", value="")
    novos_nomes = [n.strip() for n in novos_nomes_raw.splitlines() if n.strip()]
    lista_final = list(dict.fromkeys(clientes_multi + novos_nomes))
    st.write(f"Total selecionados: **{len(lista_final)}**")

    enviar_telegram_vinic = st.checkbox("Enviar card no Telegram para atendimentos do Vinicius", value=True)

    if combo:
        st.subheader("💰 Edite os valores do combo (aplicados a todos):")
        valores_customizados = {}
        for servico in combo.split("+"):
            servico_formatado = servico.strip()
            valor_padrao = obter_valor_servico(servico_formatado)
            valor = st.number_input(f"{servico_formatado} (padrão: R$ {valor_padrao})",
                                    value=valor_padrao, step=1.0, key=f"lote_{servico_formatado}")
            valores_customizados[servico_formatado] = valor

        if st.button("✅ Salvar COMBO para todos"):
            if not lista_final:
                st.warning("Selecione ou informe ao menos um cliente.")
            else:
                df_all, _ = carregar_base()
                novas = []
                for cli in lista_final:
                    # não bloqueia por duplicidade em lote; avisa
                    dup = any(ja_existe_atendimento(cli, data, s.strip(), combo) for s in combo.split("+"))
                    if dup:
                        st.warning(f"⚠️ Já existia combo para {cli} em {data}; pulando.")
                        continue
                    for s in combo.split("+"):
                        s2 = s.strip()
                        linha = {
                            "Data": data, "Serviço": s2,
                            "Valor": valores_customizados.get(s2, obter_valor_servico(s2)),
                            "Conta": conta, "Cliente": cli, "Combo": combo,
                            "Funcionário": funcionario, "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                        }
                        novas.append(_preencher_fiado_vazio(linha))
                if novas:
                    df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                    salvar_base(df_final)
                    st.success(f"✅ {len(novas)} linhas inseridas para {len(lista_final)} cliente(s).")
                    if enviar_telegram_vinic and funcionario == "Vinicius":
                        for cli in lista_final:
                            enviar_card_vinicuis(df_final, cli)
    else:
        servico_lote = st.selectbox("Serviço (aplicado a todos)", servicos_existentes)
        valor_lote = st.number_input("Valor", value=obter_valor_servico(servico_lote), step=1.0)

        if st.button("📁 Salvar SIMPLES para todos"):
            if not lista_final:
                st.warning("Selecione ou informe ao menos um cliente.")
            else:
                df_all, _ = carregar_base()
                novas = []
                for cli in lista_final:
                    if ja_existe_atendimento(cli, data, servico_lote):
                        st.warning(f"⚠️ Já existia atendimento p/ {cli} ({servico_lote}) em {data}; pulando.")
                        continue
                    nova = {
                        "Data": data, "Serviço": servico_lote, "Valor": valor_lote, "Conta": conta,
                        "Cliente": cli, "Combo": "", "Funcionário": funcionario,
                        "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                    }
                    novas.append(_preencher_fiado_vazio(nova))
                if novas:
                    df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                    salvar_base(df_final)
                    st.success(f"✅ {len(novas)} linhas inseridas para {len(lista_final)} cliente(s).")
                    if enviar_telegram_vinic and funcionario == "Vinicius":
                        for cli in lista_final:
                            enviar_card_vinicuis(df_final, cli)
