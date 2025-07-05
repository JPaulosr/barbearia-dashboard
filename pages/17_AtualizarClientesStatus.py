def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    if base_dados is None or clientes_status is None:
        return None

    # 🔄 Carrega a aba "Base de Dados" com mais segurança
    try:
        dados = base_dados.get_all_values()
        df = pd.DataFrame(dados[1:], columns=dados[0])  # pula cabeçalho
    except Exception as e:
        st.error(f"Erro ao carregar dados da planilha: {e}")
        return None

    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    # 🔍 Recupera dados atuais da aba clientes_status
    try:
        registros_atuais = clientes_status.get_all_records()
        df_atual = pd.DataFrame(registros_atuais)
    except Exception as e:
        st.error(f"Erro ao acessar aba clientes_status: {e}")
        return None

    # 🛡️ Garante colunas mínimas
    if "Cliente" not in df_atual.columns:
        df_atual["Cliente"] = []
    if "Status" not in df_atual.columns:
        df_atual["Status"] = ""
    if "Foto_URL" not in df_atual.columns:
        df_atual["Foto_URL"] = ""

    # 🔗 Junta novos clientes com existentes (sem apagar links e status)
    df_novo = pd.DataFrame({"Cliente": clientes_unicos})
    df_final = df_novo.merge(df_atual, on="Cliente", how="left")

    # 📋 Reorganiza colunas obrigatórias
    colunas = ["Cliente", "Status", "Foto_URL"]
    for col in colunas:
        if col not in df_final.columns:
            df_final[col] = ""
    df_final = df_final[colunas]

    # 🧹 Limpa e atualiza aba com a nova lista
    try:
        clientes_status.clear()
        clientes_status.update([df_final.columns.tolist()] + df_final.values.tolist())
    except Exception as e:
        st.error(f"Erro ao atualizar a aba clientes_status: {e}")
        return None

    return df_final
