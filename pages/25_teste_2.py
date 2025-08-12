    disabled_btn = not (cliente_sel and id_selecionados and forma_pag)
    if st.button("Registrar pagamento", use_container_width=True, disabled=disabled_btn):
        ss = conectar_sheets()
        ws_base = ss.worksheet(ABA_BASE)
        dfb = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).dropna(how="all")

        # garante coluna opcional de controle
        if "DataPagamento" not in dfb.columns:
            dfb["DataPagamento"] = ""

        mask = dfb.get("IDLancFiado","").isin(id_selecionados)
        if not mask.any():
            st.error("Nenhuma linha encontrada para os IDs selecionados.")
        else:
            subset = dfb[mask].copy()
            subset["Valor"] = pd.to_numeric(subset["Valor"], errors="coerce").fillna(0)
            total_pago = float(subset["Valor"].sum())

            # 🔁 ATUALIZA NO LUGAR (COMPETÊNCIA):
            # - sai de Fiado -> vira forma real
            # - limpa StatusFiado (deixa normal)
            # - registra DataPagamento (opcional)
            dfb.loc[mask, "Conta"] = forma_pag
            dfb.loc[mask, "StatusFiado"] = ""
            dfb.loc[mask, "VencimentoFiado"] = ""
            dfb.loc[mask, "DataPagamento"] = data_pag.strftime(DATA_FMT)

            salvar_df(ABA_BASE, dfb)

            # log do pagamento (mantém histórico)
            append_row(ABA_PAGT, [
                f"P-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}",
                ";".join(id_selecionados),
                data_pag.strftime(DATA_FMT),
                cliente_sel,
                forma_pag,
                total_pago,
                obs
            ])

            st.success(
                f"Pagamento registrado para **{cliente_sel}** (competência). "
                f"IDs quitados: {', '.join(id_selecionados)}. "
                f"Total: R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")
            )
            st.cache_data.clear()
