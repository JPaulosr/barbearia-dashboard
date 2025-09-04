# ⏱️ Atendimentos por Período — por DIA (Cliente+Data únicos)
import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata

st.set_page_config(page_title="Atendimentos por Período", page_icon="⏱️", layout="wide")
st.title("⏱️ Atendimentos por DIA (com Período)")

# =========================
# Helpers
# =========================
def _norm_txt(s: str) -> str:
    if pd.isna(s):
        return ""
    s = str(s).strip()
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")
    return s.lower()

# =========================
# 1) CARREGAR E PREPARAR DADOS
# =========================
@st.cache_data
def carregar_dados_google_sheets():
    url = ("https://docs.google.com/spreadsheets/d/"
           "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?"
           "tqx=out:csv&sheet=Base%20de%20Dados")
    df = pd.read_csv(url)

    # Datas em formato brasileiro
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["Data"]).copy()

    # Garante colunas
    for c in ["Cliente","Funcionário","Tipo","Combo","Período"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Normaliza Período
    norm = {
        "manha":"Manhã","manhã":"Manhã","manhã ":"Manhã","manha ":"Manhã","manha  ":"Manhã","Manha":"Manhã",
        "tarde":"Tarde","TARDE":"Tarde","tarde ":"Tarde",
        "noite":"Noite","NOITE":"Noite","noite ":"Noite"
    }
    df["Período"] = (
        df["Período"].astype(str).str.strip().map(norm)
        .where(lambda s: s.isin(["Manhã","Tarde","Noite"]), other=pd.NA)
    )

    # Colunas normalizadas para busca/tolerância
    df["Cliente_norm"] = df["Cliente"].map(_norm_txt)
    df["Func_norm"]    = df["Funcionário"].map(_norm_txt)

    # Data auxiliar
    df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Data_dia"] = df["Data_dt"].dt.floor("D")

    return df

df_raw = carregar_dados_google_sheets()
st.markdown(f"<small><i>Registros carregados: {len(df_raw)}</i></small>", unsafe_allow_html=True)

# =========================
# 2) FILTROS
# =========================
st.markdown("### 🎛️ Filtros")

col_f1, col_f2, col_f3, col_f4 = st.columns([1,1,1,1.3])

funcionarios = sorted([x for x in df_raw["Funcionário"].dropna().unique().tolist()])
periodos_opts = ["Manhã","Tarde","Noite"]
clientes_base = sorted([x for x in df_raw["Cliente"].dropna().unique().tolist()])

with col_f1:
    sel_funcs = st.multiselect("Funcionário(s)", funcionarios, default=funcionarios)

with col_f2:
    sel_periodos = st.multiselect("Período (turno)", periodos_opts, default=periodos_opts)

with col_f3:
    # multiselect com nomes existentes na base
    sel_clientes = st.multiselect("Cliente(s) (da base)", ["(Todos)"] + clientes_base, default=["(Todos)"])

with col_f4:
    q = st.text_input("🔎 Buscar cliente (tolerante a acento e caixa)", value="").strip()

# Botão para limpar filtros de cliente
c_limpar = st.button("Limpar seleção de clientes")

if c_limpar:
    sel_clientes = ["(Todos)"]
    q = ""

# Aplica filtros básicos (funcionário/turno)
df_f = df_raw.copy()
if sel_funcs:
    df_f = df_f[df_f["Funcionário"].isin(sel_funcs)]
if sel_periodos:
    df_f = df_f[df_f["Período"].isin(sel_periodos) | df_f["Período"].isna()]

# Filtro por cliente (multiselect ou busca por texto)
if sel_clientes and "(Todos)" not in sel_clientes:
    df_f = df_f[df_f["Cliente"].isin(sel_clientes)]
elif q:
    qn = _norm_txt(q)
    df_f = df_f[df_f["Cliente_norm"].str.contains(qn, na=False)]

# =========================
# 3) CONSOLIDAÇÃO — 1 atendimento por Cliente + Data
# =========================
# Tabela de unicidade Cliente+Dia (independente do Período)
unic = (
    df_f.dropna(subset=["Cliente"])
       .groupby(["Cliente","Data_dia"], as_index=False)
       .agg({"Funcionário":"first"})
)

# “Período do dia” por moda (se existir)
per_periodo = (
    df_f.dropna(subset=["Cliente","Data_dia"])
       .groupby(["Cliente","Data_dia"])["Período"]
       .agg(lambda x: x.dropna().mode().iloc[0] if x.dropna().size>0 else pd.NA)
       .reset_index()
)

base = unic.merge(per_periodo, on=["Cliente","Data_dia"], how="left")
base["Data_dt"] = base["Data_dia"]

# Dia da semana PT-BR
WEEKMAP = {0:"Segunda",1:"Terça",2:"Quarta",3:"Quinta",4:"Sexta",5:"Sábado",6:"Domingo"}
base["DiaSemana"] = base["Data_dt"].dt.weekday.map(WEEKMAP)
base["DiaSemana"] = pd.Categorical(
    base["DiaSemana"],
    categories=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"],
    ordered=True
)

# =========================
# 4) GERAL — SEMPRE MOSTRA
# =========================
st.subheader("📅 Atendimentos por DIA (abre sempre o geral)")

# Total por dia (independe de Período)
tot_por_dia = base.groupby("Data_dt", as_index=False).size().rename(columns={"size":"Total"})

# Quebra por Período (pode ter NaN — não some do total)
periodo_por_dia = (
    base.dropna(subset=["Data_dt"])
        .pivot_table(index="Data_dt", columns="Período", values="Cliente", aggfunc="count", fill_value=0)
        .reindex(columns=["Manhã","Tarde","Noite"], fill_value=0)
        .reset_index()
)

por_dia = periodo_por_dia.merge(tot_por_dia, on="Data_dt", how="outer").fillna(0)
por_dia = por_dia.sort_values("Data_dt").reset_index(drop=True)

por_dia_view = por_dia.copy()
por_dia_view["Data"] = por_dia_view["Data_dt"].dt.strftime("%d/%m/%Y")
por_dia_view = por_dia_view[["Data","Manhã","Tarde","Noite","Total"]]

c1, c2 = st.columns([1.2,1])
with c1:
    st.markdown("**Tabela — Atendimentos por dia (Cliente+Data únicos)**")
    st.dataframe(por_dia_view, use_container_width=True, hide_index=True)
with c2:
    fig_total = px.line(por_dia_view, x="Data", y="Total", markers=True, title="Total de atendimentos por dia")
    fig_total.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_total, use_container_width=True)

# =========================
# 5) RESUMOS (geral)
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
# 6) DETALHE — CLIENTE(S)
# =========================
st.subheader("👤 Detalhe por Cliente (quando selecionado)")

# Considera seleção do multiselect OU busca por texto
if (sel_clientes and "(Todos)" not in sel_clientes) or q:
    if sel_clientes and "(Todos)" not in sel_clientes:
        base_cli = base[base["Cliente"].isin(sel_clientes)].copy()
        titulo_cli = ", ".join(sel_clientes)
    else:
        qn = _norm_txt(q)
        # mapeia nomes reais que batem com a busca
        nomes_match = (df_raw.loc[df_raw["Cliente_norm"].str.contains(qn, na=False), "Cliente"]
                            .dropna().unique().tolist())
        base_cli = base[base["Cliente"].isin(nomes_match)].copy()
        titulo_cli = f'Busca: "{q}"'

    if base_cli.empty:
        st.warning("Nenhum atendimento encontrado para o(s) cliente(s) selecionado(s)/busca.")
    else:
        por_dia_cli = (
            base_cli.pivot_table(index="Data_dt", columns="Período", values="Cliente",
                                 aggfunc="count", fill_value=0)
                   .reindex(columns=["Manhã","Tarde","Noite"], fill_value=0)
                   .sort_index()
        )
        por_dia_cli["Total"] = por_dia_cli.sum(axis=1)
        por_dia_cli_view = por_dia_cli.reset_index()
        por_dia_cli_view["Data"] = por_dia_cli_view["Data_dt"].dt.strftime("%d/%m/%Y")
        por_dia_cli_view = por_dia_cli_view[["Data","Manhã","Tarde","Noite","Total"]]

        cc1, cc2 = st.columns([1.2,1])
        with cc1:
            st.markdown(f"**Atendimentos por dia — {titulo_cli}**")
            st.dataframe(por_dia_cli_view, use_container_width=True, hide_index=True)
        with cc2:
            fig_cli = px.line(por_dia_cli_view, x="Data", y="Total", markers=True,
                              title="Total por dia (cliente selecionado)")
            fig_cli.update_layout(margin=dict(t=60), title_x=0.5)
            st.plotly_chart(fig_cli, use_container_width=True)

        # Distribuições
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

        tb_cli = base_cli.copy()
        tb_cli["Data"] = tb_cli["Data_dt"].dt.strftime("%d/%m/%Y")
        st.markdown("**Visitas (1 por dia):**")
        st.dataframe(tb_cli[["Data","Cliente","Período","DiaSemana","Funcionário","Tipo","Combo"]],
                     use_container_width=True, hide_index=True)
else:
    st.info("Selecione um cliente na lista **ou** use a busca por texto para ver o detalhe.")
