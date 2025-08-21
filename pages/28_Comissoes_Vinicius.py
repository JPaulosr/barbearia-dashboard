        if pagar_caixinha and total_caixinha > 0:
            base_cx = base_jan_vini.copy()
            base_cx["ValorCxTotal"] = (
                base_cx["CaixinhaDia_num"] + base_cx["CaixinhaFundo_num"] + base_cx["CaixinhaRow_num"]
            )
            cx_por_dia = base_cx.groupby("Data", dropna=False)["ValorCxTotal"].sum().reset_index()
            for _, row in cx_por_dia.iterrows():
                data_serv = str(row["Data"]).strip()
                valf      = float(row["ValorCxTotal"])
                if valf <= 0:
                    continue
                valor_txt = f'R$ {valf:.2f}'.replace(".", ",")
                desc_txt  = f"{descricao_cx} — Pago em {to_br_date(terca_pagto)}"
                refid     = _refid_despesa(data_serv, "Vinicius", desc_txt, valf, meio_pag_cx)
                linhas.append({
                    "Data": data_serv,
                    "Prestador": "Vinicius",
                    "Descrição": desc_txt,
                    "Valor": valor_txt,
                    "Me Pag:": meio_pag_cx,
                    "RefID": refid
                })
            linhas_caixinha = int((cx_por_dia["ValorCxTotal"] > 0).sum())

        # ===== TRAVA: usa RefID em Despesas =====
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)
        existentes = set(despesas_df["RefID"].astype(str).str.strip().tolist())
        novas_linhas = []
        ignoradas = 0
        for l in linhas:
            if l["RefID"] in existentes and l["RefID"] != "":
                ignoradas += 1
                continue
            novas_linhas.append(l)
            existentes.add(l["RefID"])

        if novas_linhas:
            despesas_final = pd.concat([despesas_df, pd.DataFrame(novas_linhas)], ignore_index=True)
            colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                             [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
            despesas_final = despesas_final[colunas_finais]
            _write_df(ABA_DESPESAS, despesas_final)

            # 5) Telegram — somente se houve gravação e estiver marcado
            if enviar_tg and (dest_vini or dest_jp):
                texto = build_text_resumo(
                    period_ini=ini, period_fim=fim,
                    total_comissao_hoje=float(total_comissao_hoje),
                    total_futuros=float(total_fiados_pend),
                    pagar_caixinha=bool(pagar_caixinha),
                    total_cx=float(total_caixinha if pagar_caixinha else 0.0),
                    df_semana=semana_df, df_fiados=fiados_liberados, df_pend=fiados_pendentes,
                    total_fiado_pago_hoje=float(total_fiados),
                    qtd_fiado_pago_hoje=int(qtd_fiados_hoje)
                )
                if dest_vini: tg_send_html(texto, _get_chat_vini())
                if dest_jp:   tg_send_html(texto, _get_chat_jp())

            st.success(
                f"🎉 Pagamento registrado!\n"
                f"- Comissão (dias): {linhas_comissao}\n"
                f"- Caixinha (dias com valor): {linhas_caixinha}\n"
                f"- Gravadas em {ABA_DESPESAS}: {len(novas_linhas)} nova(s) linha(s)\n"
                f"- Ignoradas por duplicidade (RefID): {ignoradas}\n"
                f"- Cache histórico atualizado: {len(novos_cache)} item(ns)"
            )
            st.balloons()
        else:
            st.warning("Nenhuma nova linha gravada em Despesas (todas já existiam pelo RefID).")
