import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Atendimentos por Período", page_icon="⏱️", layout="wide")
st.title("⏱️ Atendimentos por Período (sem horários)")

# ============================
# 1) CARREGAR DADOS
# ============================
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    # Normalizações básicas
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    # Garante coluna Período
    if "Período" not in df.columns:
        df["Período"] = pd.NA
    # Normaliza valores de Período
    norm = {"manha":"Manhã","Manha":"Manhã","manha ":"Manhã",
            "tarde":"Tarde","noite":"Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã","Tarde","Noite"]), "Período"] = pd.NA
    return df

df = carregar_dados_google_sheets()

# Checagem mínima de colunas
colunas_necessarias = ["Cliente", "Funcionário", "Tipo", "Combo", "Data", "Período"]
faltando = [c for c in colunas_necessarias if c not in df.columns]
if faltando:
    st.error(f"As colunas obrigatórias estão faltando: {', '.join(faltando)}")
    st.stop()

st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

# ============================
# 2) FILTROS
# ============================
st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3, col_f4 = st.columns(4)

funcionarios = sorted(df["Funcionário"].dropna().unique().tolist())
periodos_opts = ["Manhã", "Tarde", "Noite"]

with col_f1:
    funcionario_selecionado = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)
with col_f2:
    cliente_busca = st.text_input("Buscar Cliente")
with col_f3:
    periodo_data = st.date_input("Período de Datas", value=None, help="Selecione um intervalo (opcional)")
with col_f4:
    periodos_sel = st.multiselect("Período (turno)", periodos_opts, default=periodos_opts)

# aplica filtros
df = df[df["Funcionário"].isin(funcionario_selecionado)]
if cliente_busca:
    df = df[df["Cliente"].astype(str).str.contains(cliente_busca, case=False, na=False)]
if isinstance(periodo_data, list) and len(periodo_data) == 2:
    df = df[(df["Data"] >= periodo_data[0]) & (df["Data"] <= periodo_data[1])]
df = df[df["Período"].isin(periodos_sel)]

# ============================
# 3) ATENDIMENTO ÚNICO POR DIA (Cliente+Data)
# ============================
# Junta combos do dia e considera 1 atendimento por Cliente+Data
base_group = df.groupby(["Cliente","Data"]).agg({
    "Funcionário":"first",
    "Tipo": lambda x: ', '.join(sorted(set([str(v) for v in x if pd.notnull(v)]))),
    "Combo": lambda x: ', '.join(sorted(set([str(v) for v in x if pd.notnull(v)]))),
    "Período": lambda x: pd.Series([v for v in x if pd.notna(v)]).mode().iloc[0] if any(pd.notna(x)) else pd.NA
}).reset_index()

# Categoria simples/combos (só por informação)
base_group["Categoria"] = base_group["Combo"].apply(lambda x: "Combo" if "+" in str(x) or "," in str(x) else "Simples")

# Cópia com Data em datetime pra gráficos por dia
base_group["Data_dt"] = pd.to_datetime(base_group["Data"], errors="coerce")

# ============================
# 4) INSIGHTS SIMPLES (ÚLTIMOS 7 DIAS)
# ============================
st.subheader("🔍 Insights da Semana (contagem de atendimentos)")
hoje = pd.Timestamp.now().normalize()
ultimos_7_dias = hoje - pd.Timedelta(days=6)
semana = base_group[
    (base_group["Data_dt"].dt.date >= ultimos_7_dias.date()) &
    (base_group["Data_dt"].dt.date <= hoje.date())
]

if not semana.empty:
    total_semana = len(semana)
    cont_periodo = semana["Período"].value_counts()
    pico_periodo = cont_periodo.idxmax() if not cont_periodo.empty else None

    top_cliente = semana["Cliente"].value_counts().idxmax()
    top_func = semana["Funcionário"].value_counts().idxmax()

    st.markdown(f"**Semana:** {ultimos_7_dias.strftime('%d/%m')} a {hoje.strftime('%d/%m')}")
    st.markdown(f"**Atendimentos na semana:** {total_semana}")
    st.markdown(f"**Período com mais atendimentos:** {pico_periodo if pico_periodo else '-'}")
    st.markdown(f"**Cliente mais frequente:** {top_cliente}")
    st.markdown(f"**Funcionário com mais atendimentos:** {top_func}")
else:
    st.markdown("Nenhum atendimento registrado nos últimos 7 dias para os filtros selecionados.")

# ============================
# 5) RANKINGS (FREQUÊNCIA)
# ============================
st.subheader("🏆 Rankings de Frequência")
col1, col2 = st.columns(2)

with col1:
    top_clientes = base_group["Cliente"].value_counts().head(10).reset_index()
    top_clientes.columns = ["Cliente","Qtd Atendimentos"]
    st.markdown("### Top 10 Clientes (por frequência)")
    st.dataframe(top_clientes, use_container_width=True)

with col2:
    top_funcionarios = base_group["Funcionário"].value_counts().head(10).reset_index()
    top_funcionarios.columns = ["Funcionário","Qtd Atendimentos"]
    st.markdown("### Top 10 Funcionários (por frequência)")
    st.dataframe(top_funcionarios, use_container_width=True)

# ============================
# 6) ATENDIMENTOS POR PERÍODO (BARRAS)
# ============================
st.subheader("📊 Atendimentos por Período")
contagem_turno = base_group["Período"].value_counts().reindex(["Manhã","Tarde","Noite"]).fillna(0).reset_index()
contagem_turno.columns = ["Período","Quantidade"]
fig_qtd_turno = px.bar(contagem_turno, x="Período", y="Quantidade", title="Quantidade de Atendimentos por Período")
fig_qtd_turno.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_qtd_turno, use_container_width=True)

# ============================
# 7) PRODUTOS vs SERVIÇOS (via Categoria)
# ============================
st.subheader("📊 Distribuição por Categoria (Simples x Combo)")
dist_cat = base_group["Categoria"].value_counts().reset_index()
dist_cat.columns = ["Categoria","Qtd"]
fig_cat = px.bar(dist_cat, x="Categoria", y="Qtd", title="Distribuição por Categoria")
fig_cat.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_cat, use_container_width=True)

# ============================
# 8) TOP DIAS COM MAIS ATENDIMENTOS
# ============================
st.subheader("📅 Dias com Mais Atendimentos")
dias_freq = base_group.groupby("Data_dt").size().reset_index(name="Qtd").dropna()
dias_freq["Data"] = dias_freq["Data_dt"].dt.strftime("%d/%m/%Y")
dias_freq = dias_freq.sort_values("Qtd", ascending=False).head(10)
dias_freq = dias_freq.sort_values("Data_dt")
fig_dias = px.bar(dias_freq, x="Data", y="Qtd", title="Top 10 Dias com Mais Atendimentos")
fig_dias.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_dias, use_container_width=True)

# ============================
# 9) HEATMAP DIA DA SEMANA x PERÍODO
# ============================
st.subheader("🔥 Mapa de Calor – Dia da Semana x Período")
tmp = base_group.dropna(subset=["Data_dt","Período"]).copy()
tmp["DiaSemana"] = tmp["Data_dt"].dt.day_name(locale="pt_BR.utf8") if hasattr(tmp["Data_dt"].dt, "day_name") else tmp["Data_dt"].dt.day_name()
# ordena manualmente
ordem = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
map_pt = {"Monday":"Segunda","Tuesday":"Terça","Wednesday":"Quarta","Thursday":"Quinta","Friday":"Sexta","Saturday":"Sábado","Sunday":"Domingo"}
tmp["DiaSemana"] = pd.Categorical(tmp["DiaSemana"].map(map_pt), categories=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"], ordered=True)

heat = tmp.pivot_table(index="DiaSemana", columns="Período", values="Cliente", aggfunc="count", fill_value=0)
heat = heat.reindex(index=["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"], columns=["Manhã","Tarde","Noite"])

fig_heat = px.imshow(heat, text_auto=True, aspect="auto", title="Atendimentos por Dia da Semana x Período")
fig_heat.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_heat, use_container_width=True)

# ============================
# 10) TABELA CONSOLIDADA
# ============================
st.subheader("📋 Visualizar dados consolidados (1 atendimento por Cliente + Data)")
cols_show = ["Data","Cliente","Funcionário","Período","Categoria","Tipo","Combo"]
tabela = base_group.copy()
tabela["Data"] = tabela["Data_dt"].dt.strftime("%d/%m/%Y")
st.dataframe(tabela[cols_show], use_container_width=True)
