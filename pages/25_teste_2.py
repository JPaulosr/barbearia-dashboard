# 11_Adicionar_Atendimento.py

import unicodedata
from datetime import datetime

import pytz
import requests
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# =========================================================
# Flags
# =========================================================
SHOW_TG_TEST = True   # <- Coloque False para esconder o bloco de teste do Telegram

# =========================================================
# Compat de cache
# =========================================================
if hasattr(st, "cache_data"):
    cache_data = st.cache_data
    cache_resource = st.cache_resource
else:
    cache_data = st.cache
    cache_resource = st.cache

# =========================================================
# CONFIG
# =========================================================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
STATUS_ABA = "clientes_status"
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

TZ = "America/Sao_Paulo"
REL_MULT = 1.5

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]

# =========================================================
# Utils
# =========================================================
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

# =========================================================
# Google Sheets
# =========================================================
@cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def ler_cabecalho(aba):
    try:
        headers = aba.row_values(1)
        return [h.strip() for h in headers] if headers else []
    except Exception:
        return []

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    for c in [*COLS_OFICIAIS, *COLS_FIADO]:
        if c not in df.columns:
            df[c] = ""
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""
    df["Combo"] = df["Combo"].fillna("")
    return df, aba

def salvar_base(df_final: pd.DataFrame):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = ler_cabecalho(aba) or [*COLS_OFICIAIS, *COLS_FIADO]
    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_FIADO]))
    for c in colunas_alvo:
        if c not in df_final.columns:
            df_final[c] = ""
    df_final = df_final[colunas_alvo]
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

# =========================================================
# Fotos (clientes_status)
# =========================================================
@cache_data(show_spinner=False)
def carregar_fotos_mapa():
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
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

# =========================================================
# Telegram (roteado por funcionário)
# =========================================================
def _has_telegram():
    return ("TELEGRAM_TOKEN" in st.secrets)

def _chat_id_default():
    # Default para JPaulo caso nada seja passado
    return st.secrets.get("TELEGRAM_CHAT_ID_JPAULO", "")

def _chat_id_por_func(funcionario: str) -> str:
    if funcionario == "Vinicius":
        return st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS", _chat_id_default())
    return st.secrets.get("TELEGRAM_CHAT_ID_JPAULO", _chat_id_default())

def tg_send(text, chat_id: str | None = None):
    if not _has_telegram():
        st.warning("Telegram não configurado.")
        return
    token = st.secrets["TELEGRAM_TOKEN"]
    chat = chat_id or _chat_id_default()
    if not chat:
        st.warning("CHAT_ID não configurado.")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        st.warning(f"Falha ao enviar Telegram: {e}")

def tg_send_photo(photo_url, caption, chat_id: str | None = None):
    if not _has_telegram():
        st.warning("Telegram não configurado.")
        return
    token = st.secrets["TELEGRAM_TOKEN"]
    chat = chat_id or _chat_id_default()
    if not chat:
        st.warning("CHAT_ID não configurado.")
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {"chat_id": chat, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=30)
    except Exception as e:
        st.warning(f"Falha ao enviar foto (Telegram): {e}")
        tg_send(caption, chat_id=chat)

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
    d = df_all[df_all["Cliente"].astype(str).str.strip() == cliente].copy()
    if d.empty:
        return None, None, "Sem média"
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

def enviar_card(df_all, cliente, funcionario):
    ultima, media, status_label = calcular_metricas_cliente(df_all, cliente)
    dias = None if ultima is None else (pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None) - ultima).days
    caption = make_card_caption(cliente, status_label, ultima, media, dias)
    foto = FOTOS.get(_norm(cliente))
    chat_id = _chat_id_por_func(funcionario)

    if foto:
        tg_send_photo(foto, caption, chat_id=chat_id)
    else:
        tg_send(caption, chat_id=chat_id)

# =========================================================
# Serviços / helpers
# =========================================================
valores_servicos = {
    "Corte": 25.0, "Pezinho": 7.0, "Barba": 15.0, "Sobrancelha": 7.0,
    "Luzes": 45.0, "Pintura": 35.0, "Alisamento": 40.0, "Gel": 10.0, "Pomada": 15.0,
}
def obter_valor_servico(servico):
    for k in valores_servicos:
        if k.lower() == servico.lower():
            return valores_servicos[k]
    return 0.0

def _preencher_fiado_vazio(linha: dict):
    for c in COLS_FIADO:
        linha.setdefault(c, "")
    return linha

def ja_existe_atendimento(cliente, data, servico, combo=""):
    df, _ = carregar_base()
    df["Combo"] = df["Combo"].fillna("")
    existe = df[(df["Cliente"] == cliente) & (df["Data"] == data) & (df["Serviço"] == servico) & (df["Combo"] == combo)]
    return not existe.empty

def sugestoes_do_cliente(df_all, cli, conta_default, periodo_default, funcionario_default):
    d = df_all[df_all["Cliente"].astype(str).str.strip() == cli].copy()
    if d.empty:
        return conta_default, periodo_default, funcionario_default
    d["_dt"] = pd.to_datetime(d["Data"], format="%d/%m/%Y", errors="coerce")
    d = d.dropna(subset=["_dt"]).sort_values("_dt")
    if d.empty:
        return conta_default, periodo_default, funcionario_default
    ultima = d.iloc[-1]
    conta = (ultima.get("Conta") or "").strip() or conta_default
    periodo = (ultima.get("Período") or "").strip() or periodo_default
    func = (ultima.get("Funcionário") or "").strip() or funcionario_default
    if periodo not in ["Manhã", "Tarde", "Noite"]: periodo = periodo_default
    if func not in ["JPaulo", "Vinicius"]: func = funcionario_default
    return conta, periodo, func

# =========================================================
# UI
# =========================================================
st.set_page_config(layout="wide")
st.title("📅 Adicionar Atendimento")

# --- Teste de Telegram (pode ocultar com SHOW_TG_TEST=False) ---
if SHOW_TG_TEST:
    with st.expander("🔔 Teste do Telegram"):
        st.caption("Teste rápido de envio para cada destino.")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            if st.button("▶️ Teste — JPaulo (privado)"):
                tg_send(f"Ping TESTE • JPaulo • {now_br()}", chat_id=st.secrets.get("TELEGRAM_CHAT_ID_JPAULO"))
                st.success("Mensagem enviada (verifique o privado do JPaulo).")
        with col_t2:
            if st.button("▶️ Teste — Vinicius (canal)"):
                tg_send(f"Ping TESTE • Vinicius • {now_br()}", chat_id=st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS"))
                st.success("Mensagem enviada (verifique o canal do Vinicius).")

df_existente, _ = carregar_base()

df_existente["_dt"] = pd.to_datetime(df_existente["Data"], format="%d/%m/%Y", errors="coerce")
df_2025 = df_existente[df_existente["_dt"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025 = df_2025[df_2025["Serviço"].notna()].copy()
servicos_existentes = sorted(df_2025["Serviço"].str.strip().unique())
contas_existentes = sorted([c for c in df_2025["Conta"].dropna().astype(str).str.strip().unique() if c])
combos_existentes = sorted([c for c in df_2025["Combo"].dropna().astype(str).str.strip().unique() if c])

# ------------ Toggle modo --------------
modo_lote = st.toggle("📦 Cadastro em Lote (vários clientes de uma vez)", value=False)

# defaults globais
col1, col2 = st.columns(2)
with col1:
    data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")
    conta_global = st.selectbox("Forma de Pagamento (padrão)", list(dict.fromkeys(contas_existentes + ["Carteira", "Nubank"])))
with col2:
    funcionario_global = st.selectbox("Funcionário (padrão)", ["JPaulo", "Vinicius"])
    tipo = st.selectbox("Tipo", ["Serviço", "Produto"])
periodo_global = st.selectbox("Período do Atendimento (padrão)", ["Manhã", "Tarde", "Noite"])
fase = "Dono + funcionário"

if not modo_lote:
    # ----------- MODO UM POR VEZ -----------
    colA, colB = st.columns(2)
    with colA:
        cliente = st.selectbox("Nome do Cliente", clientes_existentes)
    with colB:
        novo_nome = st.text_input("Ou digite um novo nome de cliente")
        cliente = novo_nome if novo_nome else cliente

    sug_conta, sug_periodo, sug_func = sugestoes_do_cliente(df_existente, cliente, conta_global, periodo_global, funcionario_global)
    conta = st.selectbox("Forma de Pagamento", list(dict.fromkeys([sug_conta] + contas_existentes + ["Carteira", "Nubank"])))
    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"], index=(0 if sug_func=="JPaulo" else 1))
    periodo_opcao = st.selectbox("Período do Atendimento", ["Manhã", "Tarde", "Noite"], index=["Manhã","Tarde","Noite"].index(sug_periodo))

    ultimo = df_existente[df_existente["Cliente"] == cliente]
    ultimo = ultimo.sort_values("Data", ascending=False).iloc[0] if not ultimo.empty else None
    combo = ""
    if ultimo is not None:
        combo = st.selectbox("Combo (último primeiro)", [""] + list(dict.fromkeys([ultimo["Combo"]] + combos_existentes)))

    if "combo_salvo" not in st.session_state: st.session_state.combo_salvo = False
    if "simples_salvo" not in st.session_state: st.session_state.simples_salvo = False
    if st.button("🧹 Limpar formulário"):
        st.session_state.combo_salvo = False; st.session_state.simples_salvo = False; st.rerun()

    if combo:
        st.subheader("💰 Edite os valores do combo antes de salvar:")
        valores_customizados = {}
        for servico in combo.split("+"):
            s2 = servico.strip()
            valores_customizados[s2] = st.number_input(
                f"{s2} (padrão: R$ {obter_valor_servico(s2)})",
                value=obter_valor_servico(s2), step=1.0, key=f"valor_{s2}"
            )
        if not st.session_state.combo_salvo and st.button("✅ Confirmar e Salvar Combo"):
            duplicado = any(ja_existe_atendimento(cliente, data, s.strip(), combo) for s in combo.split("+"))
            if duplicado:
                st.warning("⚠️ Combo já registrado para este cliente e data.")
            else:
                df_all, _ = carregar_base()
                novas = []
                for s in combo.split("+"):
                    s2 = s.strip()
                    linha = _preencher_fiado_vazio({
                        "Data": data, "Serviço": s2, "Valor": valores_customizados.get(s2, obter_valor_servico(s2)),
                        "Conta": conta, "Cliente": cliente, "Combo": combo,
                        "Funcionário": funcionario, "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                    })
                    novas.append(linha)
                df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                salvar_base(df_final)
                st.session_state.combo_salvo = True
                st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
                enviar_card(df_final, cliente, funcionario)
    else:
        st.subheader("✂️ Selecione o serviço e valor:")
        servico = st.selectbox("Serviço", servicos_existentes)
        valor = st.number_input("Valor", value=obter_valor_servico(servico), step=1.0)
        if not st.session_state.simples_salvo and st.button("📁 Salvar Atendimento"):
            if ja_existe_atendimento(cliente, data, servico):
                st.warning("⚠️ Atendimento já registrado para este cliente, data e serviço.")
            else:
                df_all, _ = carregar_base()
                nova = _preencher_fiado_vazio({
                    "Data": data, "Serviço": servico, "Valor": valor, "Conta": conta,
                    "Cliente": cliente, "Combo": "", "Funcionário": funcionario,
                    "Fase": fase, "Tipo": tipo, "Período": periodo_opcao,
                })
                df_final = pd.concat([df_all, pd.DataFrame([nova])], ignore_index=True)
                salvar_base(df_final)
                st.session_state.simples_salvo = True
                st.success(f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}.")
                enviar_card(df_final, cliente, funcionario)

else:
    # ----------- MODO LOTE AVANÇADO -----------
    st.info("Defina atendimento individual por cliente (misture combos e simples). Também escolha forma de pagamento, período e funcionário para cada um.")

    clientes_multi = st.multiselect("Clientes existentes", clientes_existentes)
    novos_nomes_raw = st.text_area("Ou cole novos nomes (um por linha)", value="")
    novos_nomes = [n.strip() for n in novos_nomes_raw.splitlines() if n.strip()]
    lista_final = list(dict.fromkeys(clientes_multi + novos_nomes))
    st.write(f"Total selecionados: **{len(lista_final)}**")

    enviar_telegram_toggle = st.checkbox("Enviar card no Telegram após salvar", value=True)

    for cli in lista_final:
        with st.container(border=True):
            st.subheader(f"⚙️ Atendimento para {cli}")
            sug_conta, sug_periodo, sug_func = sugestoes_do_cliente(df_existente, cli, conta_global, periodo_global, funcionario_global)

            tipo_at = st.radio(f"Tipo de atendimento para {cli}", ["Simples", "Combo"], horizontal=True, key=f"tipo_{cli}")

            st.selectbox(
                f"Forma de Pagamento de {cli}",
                list(dict.fromkeys([sug_conta] + contas_existentes + ["Carteira", "Nubank"])),
                key=f"conta_{cli}"
            )
            st.selectbox(
                f"Período do Atendimento de {cli}", ["Manhã", "Tarde", "Noite"],
                index=["Manhã", "Tarde", "Noite"].index(sug_periodo),
                key=f"periodo_{cli}"
            )
            st.selectbox(
                f"Funcionário de {cli}", ["JPaulo", "Vinicius"],
                index=(0 if sug_func == "JPaulo" else 1),
                key=f"func_{cli}"
            )

            if tipo_at == "Combo":
                st.selectbox(f"Combo para {cli} (formato corte+barba)", [""] + combos_existentes, key=f"combo_{cli}")
                combo_cli = st.session_state.get(f"combo_{cli}", "")
                if combo_cli:
                    for s in combo_cli.split("+"):
                        s2 = s.strip()
                        st.number_input(f"{cli} - {s2} (padrão: R$ {obter_valor_servico(s2)})",
                                        value=obter_valor_servico(s2), step=1.0, key=f"valor_{cli}_{s2}")
            else:
                st.selectbox(f"Serviço simples para {cli}", servicos_existentes, key=f"servico_{cli}")
                serv_cli = st.session_state.get(f"servico_{cli}", None)
                st.number_input(f"{cli} - Valor do serviço",
                                value=(obter_valor_servico(serv_cli) if serv_cli else 0.0),
                                step=1.0, key=f"valor_{cli}_simples")

    if st.button("💾 Salvar TODOS atendimentos"):
        if not lista_final:
            st.warning("Selecione ou informe ao menos um cliente.")
        else:
            df_all, _ = carregar_base()
            novas = []
            clientes_salvos = set()
            funcionario_por_cliente = {}  # para roteamento posterior

            for cli in lista_final:
                tipo_at = st.session_state.get(f"tipo_{cli}", "Simples")
                conta_cli = st.session_state.get(f"conta_{cli}", conta_global)
                periodo_cli = st.session_state.get(f"periodo_{cli}", periodo_global)
                func_cli = st.session_state.get(f"func_{cli}", funcionario_global)

                if tipo_at == "Combo":
                    combo_cli = st.session_state.get(f"combo_{cli}", "")
                    if not combo_cli:
                        st.warning(f"⚠️ {cli}: combo não definido. Pulando.")
                        continue
                    dup = any(ja_existe_atendimento(cli, data, s.strip(), combo_cli) for s in combo_cli.split("+"))
                    if dup:
                        st.warning(f"⚠️ {cli}: já existia COMBO em {data}. Pulando.")
                        continue
                    for s in combo_cli.split("+"):
                        s2 = s.strip()
                        val = float(st.session_state.get(f"valor_{cli}_{s2}", obter_valor_servico(s2)))
                        linha = _preencher_fiado_vazio({
                            "Data": data, "Serviço": s2, "Valor": val, "Conta": conta_cli,
                            "Cliente": cli, "Combo": combo_cli, "Funcionário": func_cli,
                            "Fase": fase, "Tipo": tipo, "Período": periodo_cli,
                        })
                        novas.append(linha)
                    clientes_salvos.add(cli)
                    funcionario_por_cliente[cli] = func_cli
                else:
                    serv_cli = st.session_state.get(f"servico_{cli}", None)
                    if not serv_cli:
                        st.warning(f"⚠️ {cli}: serviço simples não definido. Pulando.")
                        continue
                    if ja_existe_atendimento(cli, data, serv_cli):
                        st.warning(f"⚠️ {cli}: já existia atendimento simples ({serv_cli}) em {data}. Pulando.")
                        continue
                    val = float(st.session_state.get(f"valor_{cli}_simples", obter_valor_servico(serv_cli)))
                    linha = _preencher_fiado_vazio({
                        "Data": data, "Serviço": serv_cli, "Valor": val, "Conta": conta_cli,
                        "Cliente": cli, "Combo": "", "Funcionário": func_cli,
                        "Fase": fase, "Tipo": tipo, "Período": periodo_cli,
                    })
                    novas.append(linha)
                    clientes_salvos.add(cli)
                    funcionario_por_cliente[cli] = func_cli

            if not novas:
                st.warning("Nenhuma linha válida para inserir.")
            else:
                df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                salvar_base(df_final)
                st.success(f"✅ {len(novas)} linhas inseridas para {len(clientes_salvos)} cliente(s).")

                if enviar_telegram_toggle:
                    for cli in sorted(clientes_salvos):
                        enviar_card(df_final, cli, funcionario_por_cliente.get(cli, "JPaulo"))
