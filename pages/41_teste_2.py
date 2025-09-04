# ⏱️ Atendimentos por Período — por DIA (Cliente+Data únicos, usando Período da planilha)
import streamlit as st
import pandas as pd
import plotly.express as px
import unicodedata

st.set_page_config(page_title="Atendimentos por Período", page_icon="⏱️", layout="wide")
st.title("⏱️ Atendimentos por DIA (com Período da planilha)")

# =========================
# Helpers
# =========================
CATS = pd.CategoricalDtype(categories=["Manhã", "Tarde", "Noite"], ordered=True)

def _norm_txt(s: str) -> str:
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ASCII", "ignore").decode("ASCII")
    return s.strip().lower()

def _norm_periodo(x):
    """Normaliza qualquer variação (com/sem acento, maiúsculas, espaços) para Manhã/Tarde/Noite."""
    if pd.isna(x):
        return pd.NA
    s = unicodedata.normalize("NFKD", str(x)).encode("ASCII", "ignore").decode("ASCII")
    s = s.strip().lower()
    # aceita 'manha', 'manhã', 'man', 'manha ', etc.
    if s.startswith("man"):
        return "Manhã"
    if s.startswith("tar"):
        return "Tarde"
    if s.startswith("noi"):
        return "Noite"
    return pd.NA

def _periodo_moda(serie):
    """Seleciona o Período da moda; em empate usa prioridade Manhã > Tarde > Noite."""
    s = serie.dropna().astype("string")
    if s.empty:
        return pd.NA
    modos = s.mode()
    if len(modos) == 1:
        return modos.iloc[0]
    cand = pd.Series(modos).astype("category").cat.set_categories(CATS.categories, ordered=True)
    return cand.sort_values().iloc[0]

# =========================
# 1) Carregar & preparar
# =========================
@st.cache_data
def carregar_dados_google_sheets():
    url = ("https://docs.google.com/spreadsheets/d/"
           "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?"
           "tqx=out:csv&sheet=Base%20de%20Dados")
    df = pd.read_csv(url)

    # Datas (br)
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
    df = df.dropna(subset=["Data"]).copy()

    # Colunas necessárias
    for c in ["Cliente", "Funcionário", "Tipo", "Combo", "Período"]:
        if c not in df.columns:
            df[c] = pd.NA

    # Normaliza Período (agora robusto)
    df["Período"] = df["Período"].apply(_norm_periodo)

    # Auxiliares
    df["Data_dt"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Cliente_norm"] = df["Cliente"].map(_norm_txt)

    return df

df_raw = carregar_dados_google_sheets()
st.caption(f"Registros carregados: {len(df_raw)}")

# =========================
# 2) Filtros (funcionário, período, data, cliente/busca)
# =========================
st.markdown("### 🎛️ Filtros")

col_f1, col_f2, col_f3 = st.columns([1, 1, 1.2])
funcionarios = sorted([x for x in df_raw["Funcionário"].dropna().unique().tolist()])
periodos_opts = ["Manhã", "Tarde", "Noite"]

with col_f1:
    sel_funcs = st.multiselect("Funcionário(s)", funcionarios, default=funcionarios)

with col_f2:
    sel_periodos = st.multiselect("Período (turno)", periodos_opts, default=periodos_opts)

# Intervalo de datas
min_d, max_d = df_raw["Data_dt"].min().date(), df_raw["Data_dt"].max().date()
de, ate = st.date_input("Intervalo de datas", value=(min_d, max_d), min_value=min_d, max_value=max_d)

col_c1, col_c2 = st.columns([1.2, 1])
clientes_base = sorted([x for x in df_raw["Cliente"].dropna().unique().tolist()])
with col_c1:
    sel_clientes = st.multiselect("Cliente(s) (da base)", ["(Todos)"] + clientes_base, default=["(Todos)"])
with col_c2:
    q = st.text_input("🔎 Buscar cliente (tolerante a acento/caixa)", value="").strip()

# Modo de contagem
count_visita = st.toggle("Contar **Visitas únicas (Cliente+Data)** (desmarque para contar Linhas/Serviços)", value=True)

# Diagnóstico rápido
st.caption(f"Linhas SEM Período reconhecido (após normalização): {(df_raw['Período'].isna()).sum()}")

# =========================
# 3) Aplicar filtros
# =========================
df_f = df_raw.copy()

# Datas
df_f = df_f[(df_f["Data_dt"].dt.date >= de) & (df_f["Data_dt"].dt.date <= ate)]

# Funcionário
if sel_funcs:
    df_f = df_f[df_f["Funcionário"].isin(sel_funcs)]

# Período (filtro ESTRITO: só os selecionados)
if sel_periodos:
    df_f = df_f[df_f["Período"].isin(sel_periodos)]

# Clientes (lista ou busca)
if sel_clientes and "(Todos)" not in sel_clientes:
    df_f = df_f[df_f["Cliente"].isin(sel_clientes)]
elif q:
    qn = _norm_txt(q)
    df_f = df_f[df_f["Cliente_norm"].str.contains(qn, na=False)]

# =========================
# 4) Base de trabalho (VISITAS ou LINHAS)
# =========================
if count_visita:
    # VISITAS: 1 por Cliente+Data com Período = moda (empate: Manhã>Tarde>Noite)
    base = (
        df_f.groupby(["Cliente", "Data"], as_index=False)
            .agg({
                "Funcionário": "first",
                "Tipo": lambda x: ", ".join(sorted({str(v) for v in x if pd.notna(v)})),
                "Combo": lambda x: ", ".join(sorted({str(v) for v in x if pd.notna(v)})),
                "Período": _periodo_moda
            })
    )
    base["Data_dt"] = pd.to_datetime(base["Data"], errors="coerce")
else:
    # LINHAS: usa cada linha/serviço (Período da própria linha)
    base = df_f.copy()
    base["Data_dt"] = base["Data_dt"]

# Tira registros que ainda ficaram sem período (não deveriam, mas por segurança)
base["Período"] = base["Período"].where(base["Período"].isin(["Manhã", "Tarde", "Noite"]), pd.NA)

# Dia da semana
WEEKMAP = {0: "Segunda", 1: "Terça", 2: "Quarta", 3: "Quinta", 4: "Sexta", 5: "Sábado", 6: "Domingo"}
base["DiaSemana"] = base["Data_dt"].dt.weekday.map(WEEKMAP)
base["DiaSemana"] = pd.Categorical(
    base["DiaSemana"],
    categories=["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"],
    ordered=True
)

# =========================
# 5) Geral por DIA (tabela + linha)
# =========================
st.subheader("📅 Atendimentos por DIA (abre sempre o geral)")

# Total por dia
tot_por_dia = base.groupby("Data_dt", as_index=False).size().rename(columns={"size": "Total"})

# Quebra por período
periodo_por_dia = (
    base.dropna(subset=["Período"])
        .groupby(["Data_dt", "Período"], as_index=False).size()
        .pivot(index="Data_dt", columns="Período", values="size")
        .reindex(columns=["Manhã", "Tarde", "Noite"], fill_value=0)
        .reset_index()
)

por_dia = periodo_por_dia.merge(tot_por_dia, on="Data_dt", how="outer").fillna(0)
por_dia = por_dia.sort_values("Data_dt").reset_index(drop=True)

por_dia_view = por_dia.copy()
por_dia_view["Data"] = por_dia_view["Data_dt"].dt.strftime("%d/%m/%Y")
por_dia_view = por_dia_view[["Data", "Manhã", "Tarde", "Noite", "Total"]]

c1, c2 = st.columns([1.2, 1])
with c1:
    st.markdown("**Tabela — Atendimentos por dia** " + ("(Visitas únicas)" if count_visita else "(Linhas/Serviços)"))
    st.dataframe(por_dia_view, use_container_width=True, hide_index=True)
with c2:
    fig_total = px.line(por_dia_view, x="Data", y="Total", markers=True,
                        title="Total de atendimentos por dia")
    fig_total.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_total, use_container_width=True)

# =========================
# 6) Resumos (geral)
# =========================
st.subheader("📊 Resumos (Geral)")

dias_geral = base["DiaSemana"].value_counts().reindex(
    ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
).fillna(0).reset_index()
dias_geral.columns = ["Dia da Semana", "Quantidade"]

cont_periodo = base.dropna(subset=["Período"])["Período"].value_counts().reindex(["Manhã", "Tarde", "Noite"]).fillna(0).reset_index()
cont_periodo.columns = ["Período", "Quantidade"]

c3, c4 = st.columns(2)
with c3:
    st.dataframe(dias_geral, use_container_width=True, hide_index=True)
    fig_sem = px.bar(dias_geral, x="Dia da Semana", y="Quantidade",
                     title=("Atendimentos por Dia da Semana — Visitas" if count_visita else "Atendimentos por Dia da Semana — Linhas"))
    fig_sem.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_sem, use_container_width=True)
with c4:
    st.dataframe(cont_periodo, use_container_width=True, hide_index=True)
    fig_turno = px.bar(cont_periodo, x="Período", y="Quantidade",
                       title=("Atendimentos por Período — Visitas" if count_visita else "Atendimentos por Período — Linhas"))
    fig_turno.update_layout(margin=dict(t=60), title_x=0.5)
    st.plotly_chart(fig_turno, use_container_width=True)

# =========================
# 7) Detalhe por Cliente (seleção ou busca)
# =========================
st.subheader("👤 Detalhe por Cliente (quando selecionado)")

tem_sel = (sel_clientes and "(Todos)" not in sel_clientes)
tem_busca = bool(q)

if tem_sel or tem_busca:
    if tem_sel:
        base_cli = base[base["Cliente"].isin(sel_clientes)].copy()
        titulo_cli = ", ".join(sel_clientes)
    else:
        qn = _norm_txt(q)
        nomes_match = (df_raw.loc[df_raw["Cliente_norm"].str.contains(qn, na=False), "Cliente"]
                            .dropna().unique().tolist())
        base_cli = base[base["Cliente"].isin(nomes_match)].copy()
        titulo_cli = f'Busca: "{q}"'

    if base_cli.empty:
        st.warning("Nenhum atendimento encontrado para o(s) cliente(s) selecionado(s)/busca.")
    else:
        por_dia_cli = (
            base_cli.dropna(subset=["Período"])
                .groupby(["Data_dt", "Período"], as_index=False).size()
                .pivot(index="Data_dt", columns="Período", values="size")
                .reindex(columns=["Manhã", "Tarde", "Noite"], fill_value=0)
                .sort_index()
        )
        por_dia_cli["Total"] = por_dia_cli.sum(axis=1)
        por_dia_cli_view = por_dia_cli.reset_index()
        por_dia_cli_view["Data"] = por_dia_cli_view["Data_dt"].dt.strftime("%d/%m/%Y")
        por_dia_cli_view = por_dia_cli_view[["Data", "Manhã", "Tarde", "Noite", "Total"]]

        cc1, cc2 = st.columns([1.2, 1])
        with cc1:
            st.markdown(f"**Atendimentos por dia — {titulo_cli}**")
            st.dataframe(por_dia_cli_view, use_container_width=True, hide_index=True)
        with cc2:
            fig_cli = px.line(por_dia_cli_view, x="Data", y="Total", markers=True,
                              title="Total por dia (cliente selecionado)")
            fig_cli.update_layout(margin=dict(t=60), title_x=0.5)
            st.plotly_chart(fig_cli, use_container_width=True)

        # Distribuições
        por_periodo_cli = base_cli.dropna(subset=["Período"])["Período"].value_counts().reindex(["Manhã", "Tarde", "Noite"]).fillna(0).reset_index()
        por_periodo_cli.columns = ["Período", "Quantidade"]
        por_sem_cli = base_cli["DiaSemana"].value_counts().reindex(
            ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        ).fillna(0).reset_index()
        por_sem_cli.columns = ["Dia da Semana", "Quantidade"]

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
        st.markdown("**Visitas (ou Linhas, conforme o modo):**")
        st.dataframe(tb_cli[["Data", "Cliente", "Período", "DiaSemana", "Funcionário", "Tipo", "Combo"]],
                     use_container_width=True, hide_index=True)
else:
    st.info("Selecione cliente(s) na lista **ou** use a busca por texto para ver o detalhe.")
