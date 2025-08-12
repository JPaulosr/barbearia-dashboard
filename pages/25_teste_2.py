elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento — escolha o cliente e depois o(s) fiado(s) em aberto")

    df_abertos = df_base[df_base.get("StatusFiado", "") == "Em aberto"].copy()
    clientes_abertos = sorted(df_abertos["Cliente"].dropna().unique().tolist())

    colc1, colc2 = st.columns([1, 1])
    with colc1:
        cliente_sel = st.selectbox(
            "Cliente com fiado em aberto", options=[""] + clientes_abertos, index=0
        )

    # forma de pagamento (lista vinda da Base) + sugestão da última usada pelo cliente
    ultima = ultima_forma_pagto_cliente(df_base, cliente_sel) if cliente_sel else None
    lista_contas = contas_exist or ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"]
    default_idx = lista_contas.index(ultima) if (ultima in lista_contas) else 0
    with colc2:
        forma_pag = st.selectbox("Forma de pagamento", options=lista_contas, index=default_idx)

    # IDs do cliente com rótulo amigável
    ids_opcoes = []
    if cliente_sel:
        grupo_cli = df_abertos[df_abertos["Cliente"] == cliente_sel].copy()
        grupo_cli["Data"] = pd.to_datetime(grupo_cli["Data"], errors="coerce").dt.strftime(DATA_FMT)
        grupo_cli["Valor"] = pd.to_numeric(grupo_cli["Valor"], errors="coerce").fillna(0)

        def atraso_max(idval):
            v = grupo_cli.loc[grupo_cli["IDLancFiado"] == idval, "VencimentoFiado"].dropna().astype(str)
            try:
                vdt = pd.to_datetime(v.iloc[0], format=DATA_FMT, errors="coerce").date() if not v.empty else None
            except Exception:
                vdt = None
            if vdt:
                d = (date.today() - vdt).days
                return d if d > 0 else 0
            return 0

        resumo_ids = (
            grupo_cli.groupby("IDLancFiado", as_index=False)
            .agg(Data=("Data", "min"), ValorTotal=("Valor", "sum"), Qtde=("Serviço", "count"), Combo=("Combo", "first"))
        )
        for _, r in resumo_ids.iterrows():
            atraso = atraso_max(r["IDLancFiado"])
            badge = "Em dia" if atraso <= 0 else f"{int(atraso)}d atraso"
            rotulo = f"{r['IDLancFiado']} • {r['Data']} • {int(r['Qtde'])} serv. • R$ {r['ValorTotal']:.2f} • {badge}"
            if pd.notna(r["Combo"]) and str(r["Combo"]).strip():
                rotulo += f" • {r['Combo']}"
            ids_opcoes.append((r["IDLancFiado"], rotulo))

    ids_valores = [i[0] for i in ids_opcoes]
    labels = {i: l for i, l in ids_opcoes}

    # Selecionar todos
    select_all = st.checkbox("Selecionar todos os fiados deste cliente", value=False, disabled=not bool(ids_valores))
    id_selecionados = st.multiselect(
        "Selecione 1 ou mais fiados do cliente",
        options=ids_valores,
        default=(ids_valores if select_all else []),
        format_func=lambda x: labels.get(x, x),
    )

    cold1, cold2 = st.columns([1, 1])
    with cold1:
        data_pag = st.date_input("Data do pagamento", value=date.today())
    with cold2:
        obs = st.text_input("Observação (opcional)", "")

    # Resumo dos selecionados (total e por serviço)
    total_sel = 0.0
    if id_selecionados:
        subset = df_abertos[df_abertos["IDLancFiado"].isin(id_selecionados)].copy()
        subset["Valor"] = pd.to_numeric(subset["Valor"], errors="coerce").fillna(0)
        total_sel = float(subset["Valor"].sum())
        st.info(
            f"Cliente: **{cliente_sel}** • IDs: {', '.join(id_selecionados)} • "
            f"Total: **R$ {total_sel:,.2f}**".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        resumo_srv = (
            subset.groupby("Serviço", as_index=False)
            .agg(Qtd=("Serviço", "count"), Total=("Valor", "sum"))
            .sort_values(["Qtd", "Total"], ascending=[False, False])
        )
        resumo_srv["Total"] = resumo_srv["Total"].map(
            lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        st.caption("Resumo por serviço selecionado:")
        st.dataframe(resumo_srv, use_container_width=True, hide_index=True)

    # BOTÃO — QUITAR POR COMPETÊNCIA (atualiza as linhas, sem criar novas)
    disabled_btn = not (cliente_sel and id_selecionados and forma_pag)
    if st.button("Registrar pagamento", use_container_width=True, disabled=disabled_btn):
        ss = conectar_sheets()
        ws_base = ss.worksheet(ABA_BASE)
        dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")

        if "DataPagamento" not in dfb.columns:
            dfb["DataPagamento"] = ""

        mask = dfb.get("IDLancFiado", "").isin(id_selecionados)
        if not mask.any():
            st.error("Nenhuma linha encontrada para os IDs selecionados.")
        else:
            subset_all = dfb[mask].copy()
            subset_all["Valor"] = pd.to_numeric(subset_all["Valor"], errors="coerce").fillna(0)
            total_pago = float(subset_all["Valor"].sum())

            # Atualiza no lugar (competência)
            dfb.loc[mask, "Conta"] = forma_pag
            dfb.loc[mask, "StatusFiado"] = ""
            dfb.loc[mask, "VencimentoFiado"] = ""
            dfb.loc[mask, "DataPagamento"] = data_pag.strftime(DATA_FMT)

            salvar_df(ABA_BASE, dfb)

            # Log do pagamento
            append_row(
                ABA_PAGT,
                [
                    f"P-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}",
                    ";".join(id_selecionados),
                    data_pag.strftime(DATA_FMT),
                    cliente_sel,
                    forma_pag,
                    total_pago,
                    obs,
                ],
            )

            st.success(
                f"Pagamento registrado para **{cliente_sel}** (competência). "
                f"IDs quitados: {', '.join(id_selecionados)}. "
                f"Total: R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            st.cache_data.clear()
