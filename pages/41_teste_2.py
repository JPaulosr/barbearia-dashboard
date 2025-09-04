# ⏱️ Atendimentos por Período — Versão focada em turnos (Manhã/Tarde/Noite) e dia da semana
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Atendimentos por Período", page_icon="⏱️", layout="wide")
st.title("⏱️ Atendimentos por Período (Cliente + Data únicos)")

# =========================
# 1) CARREGAR E PREPARAR DADOS
# =========================
@st.cache_data
def carregar_dados_google_sheets():
    url = ("https://docs.google.com/spreadsheets/d/"
           "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?"
           "tqx=out:csv&sheet=Base%20de%20Dados")
    df = pd.read_csv(url)

    # Normalizações
    # Data -> date
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date

    # Garante coluna Período
    if "Período" not in df.columns:
        df["Período"] = pd.NA

    # Normaliza Período
    norm = {
        "manha": "Manhã", "manhã": "Manhã", "Manha": "Manhã", "manha ": "Manhã",
        "tarde": "Tarde", "TARDE": "Tarde",
        "noite": "Noite", "NOITE": "Noite"
    }
    df["Período"] = (
        df["Período"].astype(str).str.strip().map(norm).where(
            lambda s: s.isin(["Manhã","Tarde","Noite"]), other=pd.NA
        )
    )

    # Filtra registros básicos
    needed = ["Cliente","Funcionário","Tipo","Combo","Data","Período"]
    for c in needed:
        if c not in df.columns:
            df[c] = pd.NA

    # Remove linhas sem Data
    df = df.dropna(subset=["Data"])

    return df

df_raw = carregar_dados_google_sheets()

st.markdown(f"<small><i>Registros carregados: {len(df_raw)}</i></small>", unsafe_allow_html=True)

# =========================
# 2) FILTROS
# =========================
st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3, col_f4 = st.columns(4)

funcionarios = sorted([x for x in df_raw["Funcionário"].dropna().unique().tolist()])
periodos_opts = ["Manhã","Tarde","Noite"]

with col_f1:
    sel_funcs = st.multiselect("Funcionário(s)", funcionarios, default=funcionarios)

with col_f2:
    busca_cliente = st.text_input("Buscar Cliente (contém)")

with col_f3:
    intervalo = st.date_input("Intervalo de Datas (opcional)", value=None, help="Selecione início e fim")

with col_f4:
    sel_periodos = st.multiselect("Período (turno)", periodos_opts, default=periodos_opts)

df_f = df_raw.copy()
if sel_funcs:
    df_f = df_f[df_f["Funcionário"].isin(sel_funcs)]
if busca_cliente:
    df_f = df_f[df_f["Cliente"].astype(str).str.contains(busca_cliente, case=False, na=False)]
if isinstance(intervalo, list) and len(intervalo) == 2:
    df_f = df_f[(pd.to_datetime(df_f["Data"]) >= pd.to_datetime(intervalo[0])) &
                (pd.to_datetime(df_f["Data"]) <= pd.to_datetime(intervalo[1]))]
if sel_periodos:
    df_f = df_f[df_f["Período"].isin(sel_periodos)]

# =========================
# 3) CONSOLIDAÇÃO — 1 atendimento por Cliente + Data
# =========================
base = (
    df_f.groupby(["Cliente","Data"], as_index=False)
        .agg({
            "Funcionário": "first",
            "Tipo": lambda x: ", ".join(sorted(set(map(str, [v for v in x if pd.notna(v)])))),
            "Combo": lambda x: ", ".join(sorted(set(map(str, [v for v in x if pd.notna(v)])))),
            # Período = moda do dia
            "Período": lambda x: pd.Series([v for v in x if pd.notna(v)]).mode().iloc[0]
                                 if any(pd.notna(x)) else pd.NA
        })
)
base["Data_dt"] = pd.to_datetime(base["Data"], errors="coerce")

# Dia da semana estável em PT
WEEKMAP = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sábado",6:"Domingo"}
base["DiaSemanaIdx"] = base["Data_dt"].dt.weekday
base["DiaSemana"] = base["DiaSemanaIdx"].map(WEEKMAP)
base["DiaSemana"] = pd.Categorical(
    base["DiaSemana"],
    categories=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"],
    ordered=True
)

# =========================
# 4) BLOCOS PRINCIPAIS
# =========================

# 4.1 Dias da semana (Geral)
st.subheader("📅 Dias da Semana (Geral)")
dias_geral = base["DiaSemana"].value_counts().reindex(
    ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
).fillna(0).reset_index()
dias_geral.columns = ["Dia da Semana","Quantidade"]

c1, c2 = st.columns([1,1])
with c1:
    st.dataframe(dias_geral, hide_index=True, use_container_width=True)
with c2:
    fig_semana = px.bar(dias_geral, x="Dia da Semana", y="Quantidade",
                        title="Atendimentos por Dia da Semana (Geral)")
    fig_semana.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_semana, use_container_width=True)

# 4.2 Contagem por Período (Geral)
st.subheader("🕑 Atendimentos por Período (Geral)")
cont_periodo = (base["Período"].value_counts()
                .reindex(["Manhã","Tarde","Noite"])
                .fillna(0).reset_index())
cont_periodo.columns = ["Período","Quantidade"]

c3, c4 = st.columns([1,1])
with c3:
    st.dataframe(cont_periodo, hide_index=True, use_container_width=True)
with c4:
    fig_turno = px.bar(cont_periodo, x="Período", y="Quantidade",
                       title="Quantidade de Atendimentos por Período")
    fig_turno.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_turno, use_container_width=True)

# 4.3 Detalhe por Cliente (períodos + dias)
st.subheader("👤 Detalhe por Cliente")
clientes_lista = sorted(base["Cliente"].dropna().unique().tolist())
cli_sel = st.selectbox("Selecione um cliente para detalhar", ["(Nenhum)"] + clientes_lista)

if cli_sel and cli_sel != "(Nenhum)":
    base_cli = base[base["Cliente"] == cli_sel].copy()

    # Resumo do cliente
    total_visitas = len(base_cli)
    por_periodo_cli = base_cli["Período"].value_counts().reindex(["Manhã","Tarde","Noite"]).fillna(0).reset_index()
    por_periodo_cli.columns = ["Período","Quantidade"]

    por_dias_cli = base_cli["DiaSemana"].value_counts().reindex(
        ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    ).fillna(0).reset_index()
    por_dias_cli.columns = ["Dia da Semana","Quantidade"]

    st.markdown(f"**Cliente:** {cli_sel} — **Visitas únicas:** {total_visitas}")

    cc1, cc2 = st.columns(2)
    with cc1:
        fig_cli_periodo = px.bar(por_periodo_cli, x="Período", y="Quantidade",
                                 title="Períodos em que o cliente veio")
        fig_cli_periodo.update_layout(margin=dict(t=60), title_x=0.5)
        st.plotly_chart(fig_cli_periodo, use_container_width=True)

    with cc2:
        fig_cli_semana = px.bar(por_dias_cli, x="Dia da Semana", y="Quantidade",
                                title="Dias da semana que o cliente costuma vir")
        fig_cli_semana.update_layout(margin=dict(t=60), title_x=0.5)
        st.plotly_chart(fig_cli_semana, use_container_width=True)

    # Lista de visitas do cliente
    tabela_cli = base_cli.copy()
    tabela_cli["Data"] = tabela_cli["Data_dt"].dt.strftime("%d/%m/%Y")
    cols_cli = ["Data","Período","DiaSemana","Funcionário","Tipo","Combo"]
    st.markdown("**Visitas do cliente (1 por dia):**")
    st.dataframe(tabela_cli[cols_cli], use_container_width=True, hide_index=True)

# =========================
# 5) Tabela consolidada (geral)
# =========================
st.subheader("📋 Dados consolidados (1 atendimento por Cliente + Data)")
tabela = base.copy()
tabela["Data"] = tabela["Data_dt"].dt.strftime("%d/%m/%Y")
st.dataframe(
    tabela[["Data","Cliente","Funcionário","Período","DiaSemana","Tipo","Combo"]],
    use_container_width=True, hide_index=True
)
