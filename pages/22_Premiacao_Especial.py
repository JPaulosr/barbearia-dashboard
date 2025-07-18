# 👨‍👩‍👧‍👦 Cliente Família
st.subheader("👨‍👩‍👧‍👦 Cliente Família")
df_familia = df.merge(df_status[["Cliente", "Família"]], on="Cliente", how="left")
df_familia = df_familia[df_familia["Família"].notna() & (df_familia["Família"] != "")]

if not df_familia.empty:
    # Calcular o total gasto por família
    gasto_total = df_familia.groupby("Família")["Valor"].sum().sort_values(ascending=False)
    familia_top = gasto_total.index[0]
    total_gasto = gasto_total.iloc[0]

    # Filtrar só os atendimentos da família vencedora
    df_top = df_familia[df_familia["Família"] == familia_top].copy()

    # Corrigir a contagem de atendimentos com a lógica oficial
    df_top["Data"] = pd.to_datetime(df_top["Data"])
    df_top["Data_Agrupamento"] = df_top["Data"]
    corte = pd.to_datetime("2025-05-11")
    df_top["Data_Agrupamento"] = df_top.apply(
        lambda row: f"{row['Cliente']}_{row['Data'].date()}" if row["Data"] >= corte else row.name,
        axis=1
    )
    total_atendimentos = df_top["Data_Agrupamento"].nunique()
    total_dias = df_top["Data"].dt.date.nunique()
    membros_df = df_status[df_status["Família"] == familia_top]

    st.markdown(f"### 🏅 Família {familia_top.title()}")
    st.markdown(
        f"Família **{familia_top.lower()}** teve atendimentos em **{total_dias} dias diferentes**, "
        f"somando **{total_atendimentos} atendimentos individuais** e **R$ {total_gasto:.2f}** gastos entre todos os membros."
    )

    for _, row in membros_df.iterrows():
        col1, col2 = st.columns([1, 5])
        with col1:
            try:
                if pd.notna(row["Foto"]):
                    response = requests.get(row["Foto"])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, width=100)
                else:
                    raise Exception("sem imagem")
            except:
                st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=100)
        with col2:
            st.markdown(f"**{row['Cliente']}**")
else:
    st.info("Nenhuma família com atendimentos foi encontrada.")
