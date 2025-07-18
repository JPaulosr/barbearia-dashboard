# === Lista de premiados para evitar duplicação ===
clientes_premiados = set()

def gerar_top3(df_base, titulo, excluir_clientes=None):
    if excluir_clientes is None:
        excluir_clientes = set()

    col1, col2, col3 = st.columns([0.05, 0.15, 0.8])
    col1.markdown("### ")
    col2.markdown(f"#### {titulo}")

    df_base = df_base.copy()
    df_base["Valor"] = pd.to_numeric(df_base["Valor"], errors="coerce").fillna(0)

    # Agrupar por Cliente + Data para valor por atendimento
    valor_por_atendimento = df_base.groupby(["Cliente", "Data"], as_index=False)["Valor"].sum()

    # Calcular total gasto por cliente
    total_gasto_por_cliente = valor_por_atendimento.groupby("Cliente")["Valor"].sum()

    # Ordenar e remover clientes já premiados
    ranking = total_gasto_por_cliente.sort_values(ascending=False)
    ranking = ranking[~ranking.index.isin(excluir_clientes)]

    # Top 3
    top3 = ranking.head(3).index.tolist()
    medalhas = ["🥇", "🥈", "🥉"]

    for i, cliente in enumerate(top3):
        clientes_premiados.add(cliente)

        atendimentos_unicos = valor_por_atendimento[valor_por_atendimento["Cliente"] == cliente]["Data"].nunique()

        linha = st.columns([0.05, 0.12, 0.83])
        linha[0].markdown(f"### {medalhas[i]}")

        link_foto = df_fotos[df_fotos["Cliente"] == cliente]["Foto"].dropna().values
        if len(link_foto):
            try:
                response = requests.get(link_foto[0])
                img = Image.open(BytesIO(response.content))
                linha[1].image(img, width=50)
            except:
                linha[1].text("[sem imagem]")
        else:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

        linha[2].markdown(f"**{cliente.lower()}** — {atendimentos_unicos} atendimentos")

# === Top 3 Geral ===
st.subheader("Top 3 Geral")
gerar_top3(df, "")

# === Top 3 JPaulo (exclui premiados do geral) ===
st.subheader("Top 3 JPaulo")
gerar_top3(df[df["Funcionário"] == "JPaulo"], "", excluir_clientes=clientes_premiados)

# === Top 3 Vinicius (exclui premiados do geral) ===
st.subheader("Top 3 Vinicius")
gerar_top3(df[df["Funcionário"] == "Vinicius"], "", excluir_clientes=clientes_premiados)
