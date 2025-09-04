# ⏱️ Atendimentos por Período — por DIA (Cliente+Data únicos)
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Atendimentos por Período", page_icon="⏱️", layout="wide")
st.title("⏱️ Atendimentos por DIA (com Período)")

# =========================
# 1) CARREGAR E PREPARAR DADOS
# =========================
@st.cache_data
def carregar_dados_google_sheets():
    url = ("https://docs.google.com/spreadsheets/d/"
           "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?"
           "tqx=out:csv&sheet=Base%20de%20Dados")
    df = pd.read_csv(url)

    # Data -> date
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date

    # Garante colunas essenciais
    for c in ["Cliente","Funcionário","Tipo","Combo","Período"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Normaliza Período
    norm = {
        "manha":"Manhã","manhã":"Manhã","Manha":"Manhã","manha ":"Manhã",
        "tarde":"Tarde","TARDE":"Tarde",
        "noite":"Noite","NOITE":"Noite"
    }
    df["Período"] = (
        df["Período"].astype(str).str.strip().map(norm)
        .where(lambda s: s.isin(["Manhã","Tarde","Noite"]), other=pd.NA)
    )

    # Remove linhas sem Data
    df = df.dropna(subset=["Data"])
    return df

df_raw = carregar_dados_google_sheets()
st.markdown(f"<small><i>Registros carregados: {len(df_raw)}</i></small>", unsafe_allow_html=True)

# =========================
# 2) FILTROS
# =========================
st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3 = st.columns([1,1,1])

funcionarios = sorted([x for x in df_raw["Funcionário"].dropna().unique().tolist()])
periodos_opts = ["Manhã","Tarde","Noite"]
clientes_opts = ["(Todos)"] + sorted([x for x in df_raw["Cliente"].dropna().unique().tolist()])

with col_f1:
    sel_funcs = st.multiselect("Funcionário(s)", funcionarios, default=funcionarios)

with col_f2:
    sel_periodos = st.multiselect("Período (turno)", periodos_opts, default=periodos_opts)

with col_f3:
    sel_clientes = st.multiselect("Cliente(s) (da base)", clientes_opts, default=["(Todos)"])

# Aplica filtros
df_f = df_raw.copy()
if sel_funcs:
    df_f = df_f[df_f["Funcionário"].isin(sel_funcs)]
if sel_periodos:
    df_f = df_f[df_f["Período"].isin(sel_periodos)]
if sel_clientes and "(Todos)" not in sel_clientes:
    df_f = df_f[df_f["Cliente"].isin(sel_clientes)]

# =========================
# 3) CONSOLIDAÇÃO — 1 atendimento por Cliente + Data
# =========================
base = (
    df_f.groupby(["Cliente","Data"], as_index=False)
        .agg({
            "Funcionário": "first",
            "Tipo": lambda x: ", ".join(sorted(set(map(str, [v for v in x if pd.notna(v)])))),
            "Combo": lambda x: ", ".join(sorted(set(map(str, [v for v in x if pd.notna(v)])))),
            # Período = moda do dia (se existir)
            "Período": lambda x: pd.Series([v for v in x if pd.notna(v)]).mode().iloc[0]
                                 if any(pd.notna(x)) else pd.NA
        })
)
base["Data_dt"] = pd.to_datetime(base["Data"], errors="coerce")

# Dia da semana em PT
WEEKMAP = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sábado",6:"Domingo"}
base["DiaSemana"] = base["Data_dt"].dt.weekday.map(WEEKMAP)
base["DiaSemana"] = pd.Categorical(
    base["DiaSemana"],
    categories=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"],
    ordered=True
)

# =========================
# 4) TELA INICIAL — POR DIA
# =========================
st.subheader("📅 Atendimentos por DIA (abre sempre o geral)")
# Pivot por dia → colunas = períodos
por_dia = (
    base.pivot_table(
        index="Data_dt", columns="Período", values="Cliente",
        aggfunc="count", fill_value=0
    )
    .reindex(columns=["Manhã","Tarde","Noite"], fill_value=0)
    .sort_index()
)
por_dia["Total"] = por_dia.sum(axis=1)
por_dia_view = por_dia.reset_index()
por_dia_view["Data"] = por_dia_view["Data_dt"].dt.strftime("%d/%m/%Y")
por_dia_view = por_dia_view[["Data","Manhã","Tarde","Noite","Total"]]

c1, c2 = st.columns([1.2,1])
with c1:
    st.markdown("**Tabela — Atendimentos por dia (Cliente+Data únicos)**")
    st.dataframe(por_dia_view, use_container_width=True, hide_index=True)
with c2:
    fig_total = px.line(por_dia_view, x="Data", y="Total", markers=True,
                        title="Total de atendimentos por dia")
    fig_total.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_total, use_container_width=True)

# =========================
# 5) DIAS DA SEMANA (geral) e PERÍODO (geral)
# =========================
st.subheader("📊 Resumos (Geral)")

dias_geral = base["DiaSemana"].value_counts().reindex(
    ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
).fillna(0).reset_index()
dias_geral.columns = ["Dia da Semana","Quantidade"]

cont_periodo = base["Período"].value_counts().reindex(["Manhã","Tarde","Noite"]).fillna(0).reset_index()
cont_periodo.columns = ["Período","Quantidade"]

c3, c4 = st.columns(2)
with c3:
    st.dataframe(dias_geral, use_container_width=True, hide_index=True)
    fig_sem = px.bar(dias_geral, x="Dia da Semana", y="Quantidade", title="Atendimentos por Dia da Semana (Geral)")
    fig_sem.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_sem, use_container_width=True)
with c4:
    st.dataframe(cont_periodo, use_container_width=True, hide_index=True)
    fig_turno = px.bar(cont_periodo, x="Período", y="Quantidade", title="Atendimentos por Período (Geral)")
    fig_turno.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_turno, use_container_width=True)

# =========================
# 6) DETALHE — CLIENTE(S) SELECIONADO(S)
# =========================
st.subheader("👤 Detalhe por Cliente (quando selecionado)")

if sel_clientes and "(Todos)" not in sel_clientes:
    base_cli = base[base["Cliente"].isin(sel_clientes)].copy()

    # Tabela por dia para o(s) cliente(s)
    por_dia_cli = (
        base_cli.pivot_table(
            index="Data_dt", columns="Período", values="Cliente",
            aggfunc="count", fill_value=0
        )
        .reindex(columns=["Manhã","Tarde","Noite"], fill_value=0)
        .sort_index()
    )
    por_dia_cli["Total"] = por_dia_cli.sum(axis=1)
    por_dia_cli_view = por_dia_cli.reset_index()
    por_dia_cli_view["Data"] = por_dia_cli_view["Data_dt"].dt.strftime("%d/%m/%Y")
    por_dia_cli_view = por_dia_cli_view[["Data","Manhã","Tarde","Noite","Total"]]

    cc1, cc2 = st.columns([1.2,1])
    with cc1:
        st.markdown(f"**Atendimentos por dia — {', '.join(sel_clientes)}**")
        st.dataframe(por_dia_cli_view, use_container_width=True, hide_index=True)
    with cc2:
        fig_cli = px.line(por_dia_cli_view, x="Data", y="Total", markers=True,
                          title="Total por dia (cliente selecionado)")
        fig_cli.update_layout(margin=dict(t=60), title_x=0.5)
        st.plotly_chart(fig_cli, use_container_width=True)

    # Distribuições do(s) cliente(s)
    por_periodo_cli = base_cli["Período"].value_counts().reindex(["Manhã","Tarde","Noite"]).fillna(0).reset_index()
    por_periodo_cli.columns = ["Período","Quantidade"]
    por_sem_cli = base_cli["DiaSemana"].value_counts().reindex(
        ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    ).fillna(0).reset_index()
    por_sem_cli.columns = ["Dia da Semana","Quantidade"]

    cc3, cc4 = st.columns(2)
    with cc3:
        fig_p_cli = px.bar(por_periodo_cli, x="Período", y="Quantidade", title="Períodos do(s) cliente(s)")
        fig_p_cli.update_layout(margin=dict(t=60), title_x=0.5)
        st.plotly_chart(fig_p_cli, use_container_width=True)
    with cc4:
        fig_s_cli = px.bar(por_sem_cli, x="Dia da Semana", y="Quantidade", title="Dias da semana do(s) cliente(s)")
        fig_s_cli.update_layout(margin=dict(t=60), title_x=0.5)
        st.plotly_chart(fig_s_cli, use_container_width=True)

    # Lista de visitas do(s) cliente(s)
    tb_cli = base_cli.copy()
    tb_cli["Data"] = tb_cli["Data_dt"].dt.strftime("%d/%m/%Y")
    st.markdown("**Visitas (1 por dia):**")
    st.dataframe(tb_cli[["Data","Cliente","Período","DiaSemana","Funcionário","Tipo","Combo"]],
                 use_container_width=True, hide_index=True)
else:
    st.info("Selecione um ou mais clientes em **Cliente(s) (da base)** para ver o detalhe.")
