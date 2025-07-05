def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    if base_dados is None or clientes_status is None:
        return None

    # 🔹 Pega os dados da aba Base de Dados
    dados = base_dados.get_all_records()
    df = pd.DataFrame(dados)

    if df.empty or "Cliente" not in df.columns:
        st.warning("⚠️ Não foi possível encontrar clientes na base de dados.")
        return None

    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    # 🔹 Lê a aba clientes_status atual
    registros_atuais = clientes_status.get_all_records()
    df_atual = pd.DataFrame(registros_atuais)

    # Se ainda não existe nada na planilha
    if df_atual.empty:
        df_atual = pd.DataFrame(columns=["Cliente", "Status", "Foto_URL"])

    # 🔹 Garante colunas obrigatórias
    for coluna in ["Cliente", "Status", "Foto_URL"]:
        if coluna not in df_atual.columns:
            df_atual[coluna] = ""

    # 🔹 Cria nova lista de clientes a partir da base e preserva dados existentes
    df_novo = pd.DataFrame({"Cliente": clientes_unicos})
    df_final = df_novo.merge(df_atual, on="Cliente", how="left")

    # 🔹 Preenche valores vazios com string vazia
    df_final["Status"] = df_final["Status"].fillna("")
    df_final["Foto_URL"] = df_final["Foto_URL"].fillna("")

    # 🔹 Reorganiza colunas
    df_final = df_final[["Cliente", "Status", "Foto_URL"]]

    # 🔹 Atualiza planilha
    clientes_status.clear()
    clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())

    return df_final
