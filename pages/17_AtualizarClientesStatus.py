def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    if base_dados is None or clientes_status is None:
        return None

    # Carrega clientes únicos da base de dados
    dados = base_dados.get_all_records()
    df = pd.DataFrame(dados)
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    # Carrega conteúdo atual da aba clientes_status
    registros_atuais = clientes_status.get_all_records()
    df_atual = pd.DataFrame(registros_atuais)

    # Garante colunas mínimas
    if "Cliente" not in df_atual.columns:
        df_atual["Cliente"] = []
    if "Status" not in df_atual.columns:
        df_atual["Status"] = ""
    if "Foto_URL" not in df_atual.columns:
        df_atual["Foto_URL"] = ""

    # Junta com novos clientes, preservando status e foto já existentes
    df_novo = pd.DataFrame({"Cliente": clientes_unicos})
    df_final = df_novo.merge(df_atual, on="Cliente", how="left")

    # Reorganiza colunas
    colunas = ["Cliente", "Status", "Foto_URL"]
    for col in colunas:
        if col not in df_final.columns:
            df_final[col] = ""

    df_final = df_final[colunas]

    # Atualiza aba com os novos dados
    clientes_status.clear()
    clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())
    return df_final
