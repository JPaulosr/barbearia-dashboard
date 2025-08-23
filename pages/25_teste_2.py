# =========================
# KPIs (RESPONSIVO, SEM TICKET)
# =========================
cli, srv, rec, tkt = kpis(df_dia)

# CSS para cards responsivos (empilham no celular)
st.markdown("""
<style>
.metrics-wrap{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
.metrics-wrap .card{
  background:rgba(255,255,255,0.04);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px;
  padding:12px 14px;
  min-width:160px; /* evita cortar no mobile */
  flex:1 1 200px;  /* cresce e quebra em novas linhas quando precisa */
}
.metrics-wrap .card .label{font-size:0.9rem;opacity:.85;margin-bottom:6px}
.metrics-wrap .card .value{
  font-weight:700;
  /* fonte que cresce no desktop e reduz no celular */
  font-size:clamp(18px, 3.8vw, 28px);
  line-height:1.15;
  word-break:break-word;  /* garante quebra e nunca "R$ 2..." */
}
.section-h{font-weight:700;margin:12px 0 6px}
</style>
""", unsafe_allow_html=True)

def metric_card(label, value):
    return f"""
    <div class="card">
      <div class="label">{label}</div>
      <div class="value">{value}</div>
    </div>
    """

st.markdown('<div class="metrics-wrap">' +
            metric_card("👥 Clientes atendidos", f"{cli}") +
            metric_card("✂️ Serviços realizados", f"{srv}") +
            metric_card("💰 Receita do dia", format_moeda(rec)) +
            '</div>', unsafe_allow_html=True)

st.markdown("---")

# =========================
# Por Funcionário (RESPONSIVO, SEM TICKET)
# =========================
st.subheader("📊 Por Funcionário (dia selecionado)")

df_j = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_JPAULO.casefold()]
df_v = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_VINICIUS.casefold()]

cli_j, srv_j, rec_j, _ = kpis(df_j)
cli_v, srv_v, rec_v, _ = kpis(df_v)

col_j, col_v = st.columns(2)

with col_j:
    st.markdown(f'<div class="section-h">{FUNC_JPAULO}</div>', unsafe_allow_html=True)
    st.markdown('<div class="metrics-wrap">' +
                metric_card("Clientes", f"{cli_j}") +
                metric_card("Serviços", f"{srv_j}") +
                metric_card("Receita", format_moeda(rec_j)) +
                '</div>', unsafe_allow_html=True)

with col_v:
    st.markdown(f'<div class="section-h">{FUNC_VINICIUS}</div>', unsafe_allow_html=True)
    st.markdown('<div class="metrics-wrap">' +
                metric_card("Clientes", f"{cli_v}") +
                metric_card("Serviços", f"{srv_v}") +
                metric_card("Receita", format_moeda(rec_v)) +
                '</div>', unsafe_allow_html=True)

# =========================
# Gráfico comparativo (mantido)
# =========================
df_comp = pd.DataFrame([
    {"Funcionário": FUNC_JPAULO, "Clientes": cli_j, "Serviços": srv_j},
    {"Funcionário": FUNC_VINICIUS, "Clientes": cli_v, "Serviços": srv_v},
])
fig = px.bar(
    df_comp.melt(id_vars="Funcionário", var_name="Métrica", value_name="Quantidade"),
    x="Funcionário", y="Quantidade", color="Métrica", barmode="group",
    title=f"Comparativo de atendimentos — {dia_selecionado.strftime('%d/%m/%Y')}"
)
st.plotly_chart(fig, use_container_width=True)
