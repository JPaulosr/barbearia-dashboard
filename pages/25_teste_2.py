# 12_Fiado.py
# Página de FIADO para barbearia — registro de débitos, pagamentos, limites e saldos
# ✔ Integra Google Sheets (mesma planilha do projeto)
# ✔ Cria as abas automaticamente se não existirem
# ✔ Busca lista de clientes da própria planilha (Base de Dados e clientes_status)
# ✔ Aplica limite por cliente (coluna 'LimiteFiado' em clientes_status) com fallback padrão
# ✔ Mostra saldos, pendências, atrasos, filtros, exportação
# ✔ Operações: novo fiado, registrar pagamento, quitar total, editar limite rápido

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, date
from io import BytesIO
import pytz

# =========================
# CONFIG BÁSICA DA PÁGINA
# =========================
st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide")
st.title("💳 Controle de Fiado")

# Id da planilha principal (mesma do projeto)
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

# Nomes das abas usadas
ABA_LANC = "Fiado_Lancamentos"     # lançamentos de fiado (dívidas)
ABA_PAGT = "Fiado_Pagamentos"      # pagamentos efetuados
ABA_STATUS = "clientes_status"     # onde opcionalmente mora o 'LimiteFiado'
ABA_BASE = "Base de Dados"         # para lista de clientes

# Padrões
TZ = pytz.timezone("America/Sao_Paulo")
LIMITE_PADRAO = 150.0  # valor padrão se cliente não tiver limite definido no clientes_status

# =========================
# CONEXÃO GOOGLE SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def garantir_aba(planilha, nome_aba, colunas):
    try:
        ws = planilha.worksheet(nome_aba)
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet(title=nome_aba, rows=100, cols=max(10, len(colunas)))
        ws.append_row(colunas)
    # Garante cabeçalho correto
    cabecalho = ws.row_values(1)
    if cabecalho != colunas:
        # se estiver vazio, escreve cabeçalho
        if len(cabecalho) == 0:
            ws.append_row(colunas)
        else:
            # baixa dados existentes e reescreve com cabeçalho correto
            df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
            df = df.dropna(how="all")
            out = pd.DataFrame(columns=colunas)
            if not df.empty:
                # realinha colunas (mantém as que existem)
                for c in df.columns:
                    if c in out.columns:
                        out[c] = df[c]
            ws.clear()
            set_with_dataframe(ws, out)

    return planilha.worksheet(nome_aba)

@st.cache_data
def carregar_tudo():
    ss = conectar_sheets()

    # Cria/garante as abas de trabalho
    col_lanc = ["Data", "Cliente", "Descricao", "Valor", "Vencimento", "Funcionario", "FormaPagamentoPrevista", "IDLanc"]
    col_pagt = ["Data", "Cliente", "Valor", "Observacao", "IDPagamento"]
    ws_lanc = garantir_aba(ss, ABA_LANC, col_lanc)
    ws_pagt = garantir_aba(ss, ABA_PAGT, col_pagt)

    # Carrega dados
    df_lanc = get_as_dataframe(ws_lanc, evaluate_formulas=True, header=0).dropna(how="all")
    df_pagt = get_as_dataframe(ws_pagt, evaluate_formulas=True, header=0).dropna(how="all")

    # Tipagem e defaults
    for c in ["Data", "Vencimento"]:
        if c in df_lanc.columns:
            df_lanc[c] = pd.to_datetime(df_lanc[c], errors="coerce").dt.date
    if "Valor" in df_lanc.columns:
        df_lanc["Valor"] = pd.to_numeric(df_lanc["Valor"], errors="coerce").fillna(0.0)
    if "IDLanc" not in df_lanc.columns:
        df_lanc["IDLanc"] = ""

    if "Data" in df_pagt.columns:
        df_pagt["Data"] = pd.to_datetime(df_pagt["Data"], errors="coerce").dt.date
    if "Valor" in df_pagt.columns:
        df_pagt["Valor"] = pd.to_numeric(df_pagt["Valor"], errors="coerce").fillna(0.0)
    if "IDPagamento" not in df_pagt.columns:
        df_pagt["IDPagamento"] = ""

    # Clientes existentes
    df_status = pd.DataFrame()
    try:
        df_status = get_as_dataframe(ss.worksheet(ABA_STATUS), evaluate_formulas=True, header=0).dropna(how="all")
    except gspread.WorksheetNotFound:
        pass

    df_base = pd.DataFrame()
    try:
        df_base = get_as_dataframe(ss.worksheet(ABA_BASE), evaluate_formulas=True, header=0).dropna(how="all")
    except gspread.WorksheetNotFound:
        pass

    # Monta lista única de clientes
    clientes = set()
    if not df_status.empty and "Cliente" in df_status.columns:
        clientes.update(df_status["Cliente"].dropna().astype(str).str.strip())
    if not df_base.empty and "Cliente" in df_base.columns:
        clientes.update(df_base["Cliente"].dropna().astype(str).str.strip())
    if "Cliente" in df_lanc.columns:
        clientes.update(df_lanc["Cliente"].dropna().astype(str).str.strip())
    if "Cliente" in df_pagt.columns:
        clientes.update(df_pagt["Cliente"].dropna().astype(str).str.strip())
    clientes = sorted([c for c in clientes if c])

    # Limites por cliente a partir de clientes_status
    limites = {}
    if not df_status.empty:
        if "Cliente" in df_status.columns:
            if "LimiteFiado" in df_status.columns:
                for _, r in df_status.iterrows():
                    nome = str(r.get("Cliente", "")).strip()
                    lim = r.get("LimiteFiado", None)
                    try:
                        lim = float(str(lim).replace(",", "."))
                    except:
                        lim = None
                    if nome:
                        limites[nome] = lim

    return df_lanc, df_pagt, clientes, limites

def atualizar_df_na_aba(nome_aba, df):
    ss = conectar_sheets()
    ws = ss.worksheet(nome_aba)
    ws.clear()
    set_with_dataframe(ws, df)

def append_linha(nome_aba, lista_valores):
    ss = conectar_sheets()
    ws = ss.worksheet(nome_aba)
    ws.append_row(lista_valores, value_input_option="USER_ENTERED")

# =========================
# FUNÇÕES DE NEGÓCIO
# =========================
def gerar_id(prefixo):
    agora = datetime.now(TZ).strftime("%Y%m%d%H%M%S%f")[:-3]
    return f"{prefixo}-{agora}"

def saldo_cliente(df_lanc, df_pagt, cliente):
    debito = df_lanc.loc[df_lanc["Cliente"]==cliente, "Valor"].sum() if not df_lanc.empty else 0.0
    credito = df_pagt.loc[df_pagt["Cliente"]==cliente, "Valor"].sum() if not df_pagt.empty else 0.0
    return round(debito - credito, 2)

def df_saldos(df_lanc, df_pagt):
    clientes = sorted(set(df_lanc["Cliente"].dropna().astype(str)) | set(df_pagt["Cliente"].dropna().astype(str)))
    rows = []
    for c in clientes:
        rows.append({"Cliente": c, "Saldo": saldo_cliente(df_lanc, df_pagt, c)})
    return pd.DataFrame(rows).sort_values("Saldo", ascending=False)

def obter_limite_cliente(limites, cliente):
    lim = limites.get(cliente, None)
    return lim if (lim is not None and lim > 0) else LIMITE_PADRAO

def atrasados(df_lanc, df_pagt):
    hoje = date.today()
    if df_lanc.empty:
        return pd.DataFrame(columns=["Cliente","Descricao","Valor","Vencimento","DiasAtraso"])
    # Calcula pago por cliente para deduzir do mais antigo
    # Estratégia simples: saldo > 0 e vencimento < hoje => atrasado
    df = df_lanc.copy()
    df["PagoAcum"] = 0.0
    # Monta um DF por cliente ordenado por vencimento (FIFO) e abate pagamentos
    saida = []
    for cliente in sorted(df["Cliente"].dropna().unique()):
        dfl = df[df["Cliente"]==cliente].sort_values("Vencimento")
        total_pago = df_pagt[df_pagt["Cliente"]==cliente]["Valor"].sum() if not df_pagt.empty else 0.0
        for _, r in dfl.iterrows():
            valor = float(r.get("Valor",0.0))
            if total_pago >= valor:
                total_pago -= valor
                resto = 0.0
            else:
                resto = valor - total_pago
                total_pago = 0.0
            if resto > 0 and pd.notna(r.get("Vencimento")) and r["Vencimento"] < hoje:
                dias = (hoje - r["Vencimento"]).days
                saida.append({
                    "Cliente": cliente,
                    "Descricao": r.get("Descricao",""),
                    "Valor": round(resto,2),
                    "Vencimento": r["Vencimento"],
                    "DiasAtraso": dias
                })
    if not saida:
        return pd.DataFrame(columns=["Cliente","Descricao","Valor","Vencimento","DiasAtraso"])
    return pd.DataFrame(saida).sort_values(["DiasAtraso","Vencimento"], ascending=[False, True])

# =========================
# CARREGA DADOS
# =========================
df_lanc, df_pagt, clientes_lista, limites_dict = carregar_tudo()

# =========================
# SIDEBAR – AÇÕES
# =========================
st.sidebar.header("Ações")
acao = st.sidebar.radio("O que deseja fazer?", ["📌 Novo fiado", "✅ Registrar pagamento", "🧾 Saldos & atrasos", "⚙️ Ajustes de limite"])

# =========================
# AÇÃO: NOVO FIADO
# =========================
if acao == "📌 Novo fiado":
    st.subheader("📌 Lançar novo fiado (débito)")
    col1, col2 = st.columns(2)
    with col1:
        cliente = st.selectbox("Cliente", options=[""] + clientes_lista, index=0, help="Digite para buscar. Pode cadastrar manualmente se não existir.")
        if not cliente:
            cliente = st.text_input("Ou digite o nome do cliente", value="")
        descricao = st.text_input("Descrição (ex.: Corte + Barba)", "")
        valor = st.number_input("Valor (R$)", min_value=0.0, step=5.0, format="%.2f")
    with col2:
        data_lanc = st.date_input("Data do lançamento", value=date.today())
        vencimento = st.date_input("Vencimento (opcional)", value=date.today())
        funcionario = st.text_input("Funcionário", value="JPaulo")
        forma_prevista = st.selectbox("Forma de pagamento prevista", ["", "Dinheiro", "Pix", "Cartão", "Transferência", "Outro"])

    if st.button("➕ Registrar fiado", use_container_width=True):
        if not cliente or valor <= 0:
            st.error("Informe cliente e valor válido.")
        else:
            # checa limite
            limite = obter_limite_cliente(limites_dict, cliente)
            saldo_atual = saldo_cliente(df_lanc, df_pagt, cliente)
            if saldo_atual + valor > limite:
                st.error(f"Limite estourado: saldo atual R$ {saldo_atual:.2f} + novo R$ {valor:.2f} > limite R$ {limite:.2f}")
            else:
                idl = gerar_id("L")
                append_linha(
                    ABA_LANC,
                    [
                        data_lanc.strftime("%Y-%m-%d"),
                        cliente.strip(),
                        descricao.strip(),
                        valor,
                        vencimento.strftime("%Y-%m-%d") if vencimento else "",
                        funcionario.strip(),
                        forma_prevista,
                        idl
                    ]
                )
                st.success(f"Fiado registrado para **{cliente}** no valor de **R$ {valor:.2f}** (IDLanc: {idl}).")
                st.cache_data.clear()

# =========================
# AÇÃO: REGISTRAR PAGAMENTO
# =========================
elif acao == "✅ Registrar pagamento":
    st.subheader("✅ Registrar pagamento de fiado")
    col1, col2 = st.columns(2)
    with col1:
        cliente_p = st.selectbox("Cliente", options=clientes_lista)
        hoje = date.today()
        data_p = st.date_input("Data do pagamento", value=hoje)
    with col2:
        saldo = saldo_cliente(df_lanc, df_pagt, cliente_p) if cliente_p else 0.0
        valor_p = st.number_input(f"Valor pago (Saldo atual: R$ {saldo:.2f})", min_value=0.0, step=5.0, format="%.2f")
        obs = st.text_input("Observação", value="")

    colb1, colb2 = st.columns(2)
    if colb1.button("💰 Registrar pagamento", use_container_width=True):
        if not cliente_p or valor_p <= 0:
            st.error("Informe cliente e valor de pagamento válido.")
        else:
            idp = gerar_id("P")
            append_linha(
                ABA_PAGT,
                [
                    data_p.strftime("%Y-%m-%d"),
                    cliente_p.strip(),
                    valor_p,
                    obs.strip(),
                    idp
                ]
            )
            st.success(f"Pagamento de **R$ {valor_p:.2f}** registrado para **{cliente_p}** (IDPagamento: {idp}).")
            st.cache_data.clear()

    if colb2.button("✅ Quitar tudo (pagar saldo total)", type="secondary", use_container_width=True, disabled=(saldo <= 0.0)):
        if saldo > 0:
            idp = gerar_id("P")
            append_linha(
                ABA_PAGT,
                [
                    hoje.strftime("%Y-%m-%d"),
                    cliente_p.strip(),
                    saldo,
                    "Quitação total",
                    idp
                ]
            )
            st.success(f"Saldo total **R$ {saldo:.2f}** quitado para **{cliente_p}** (IDPagamento: {idp}).")
            st.cache_data.clear()
        else:
            st.info("Cliente já está com saldo zerado.")

# =========================
# AÇÃO: SALDOS & ATRASOS
# =========================
elif acao == "🧾 Saldos & atrasos":
    st.subheader("🧾 Saldos por cliente")
    df_s = df_saldos(df_lanc, df_pagt) if not df_lanc.empty or not df_pagt.empty else pd.DataFrame(columns=["Cliente","Saldo"])

    filtro_nome = st.text_input("Filtrar por nome", "")
    min_saldo = st.number_input("Saldo mínimo", value=0.0, step=10.0)
    if not df_s.empty:
        df_show = df_s.copy()
        if filtro_nome.strip():
            df_show = df_show[df_show["Cliente"].str.contains(filtro_nome.strip(), case=False, na=False)]
        df_show = df_show[df_show["Saldo"] >= min_saldo]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        total_aberto = df_show["Saldo"].sum()
        st.metric("Total em aberto (após filtros)", f"R$ {total_aberto:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

        # Exportação
        buf = BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df_show.to_excel(writer, index=False, sheet_name="Saldos")
        st.download_button("⬇️ Exportar saldos (Excel)", data=buf.getvalue(), file_name="saldos_fiado.xlsx")

    st.markdown("---")
    st.subheader("⏰ Atrasados")
    df_a = atrasados(df_lanc, df_pagt)
    if df_a.empty:
        st.success("Nenhum fiado atrasado 🎉")
    else:
        st.dataframe(df_a, use_container_width=True, hide_index=True)
        total_atrasado = df_a["Valor"].sum()
        st.metric("Total atrasado", f"R$ {total_atrasado:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

        buf2 = BytesIO()
        with pd.ExcelWriter(buf2, engine="xlsxwriter") as writer:
            df_a.to_excel(writer, index=False, sheet_name="Atrasados")
        st.download_button("⬇️ Exportar atrasados (Excel)", data=buf2.getvalue(), file_name="atrasados_fiado.xlsx")

# =========================
# AÇÃO: AJUSTES DE LIMITE
# =========================
elif acao == "⚙️ Ajustes de limite":
    st.subheader("⚙️ Limites por cliente (usa aba clientes_status → coluna 'LimiteFiado')")
    st.info("Se o cliente não tiver 'LimiteFiado' definido, uso o padrão: R$ {:.2f}".format(LIMITE_PADRAO))

    # Tabela resumida: Cliente | Limite atual | Saldo | Espaço disponível
    rows = []
    for c in sorted(clientes_lista):
        lim = obter_limite_cliente(limites_dict, c)
        sal = saldo_cliente(df_lanc, df_pagt, c)
        disp = round(lim - sal, 2)
        rows.append({"Cliente": c, "LimiteAtual": lim, "Saldo": sal, "Disponivel": disp})
    df_lim = pd.DataFrame(rows)
    st.dataframe(df_lim, use_container_width=True, hide_index=True)

    st.markdown("#### Atualizar limite de um cliente")
    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        cli = st.selectbox("Cliente", options=clientes_lista)
    with col2:
        novo_limite = st.number_input("Novo limite (R$)", min_value=0.0, step=10.0, format="%.2f")
    with col3:
        aplicar = st.button("💾 Salvar limite", use_container_width=True)

    if aplicar:
        ss = conectar_sheets()
        try:
            ws = ss.worksheet(ABA_STATUS)
        except gspread.WorksheetNotFound:
            ws = ss.add_worksheet(title=ABA_STATUS, rows=1000, cols=10)
            ws.append_row(["Cliente", "Status", "Imagem", "LimiteFiado"])

        df_status = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
        if df_status.empty:
            df_status = pd.DataFrame(columns=["Cliente","Status","Imagem","LimiteFiado"])

        if "Cliente" not in df_status.columns:
            df_status["Cliente"] = []
        if "LimiteFiado" not in df_status.columns:
            df_status["LimiteFiado"] = []

        # Atualiza ou cria linha
        idx = None
        if not df_status.empty:
            poss = df_status.index[df_status["Cliente"].astype(str).str.strip().str.lower() == cli.strip().lower()].tolist()
            idx = poss[0] if poss else None

        if idx is None:
            df_status = pd.concat([
                df_status,
                pd.DataFrame([{"Cliente": cli, "LimiteFiado": novo_limite}])
            ], ignore_index=True)
        else:
            df_status.loc[idx, "LimiteFiado"] = novo_limite

        atualizar_df_na_aba(ABA_STATUS, df_status)
        st.success(f"Limite de **{cli}** atualizado para **R$ {novo_limite:.2f}**.")
        st.cache_data.clear()

# =========================
# RODAPÉ – VISÃO RÁPIDA
# =========================
st.markdown("---")
colk1, colk2, colk3, colk4 = st.columns(4)
total_debitos = df_lanc["Valor"].sum() if not df_lanc.empty else 0.0
total_pagos = df_pagt["Valor"].sum() if not df_pagt.empty else 0.0
em_aberto = total_debitos - total_pagos
qtd_clientes_em_aberto = (df_saldos(df_lanc, df_pagt)["Saldo"] > 0).sum() if (not df_lanc.empty or not df_pagt.empty) else 0

colk1.metric("Débitos lançados", f"R$ {total_debitos:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
colk2.metric("Pagamentos registrados", f"R$ {total_pagos:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
colk3.metric("Em aberto", f"R$ {em_aberto:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
colk4.metric("Clientes devendo", f"{qtd_clientes_em_aberto}")
