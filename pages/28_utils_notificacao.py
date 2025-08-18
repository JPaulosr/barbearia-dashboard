# 2) Lança em DESPESAS: UMA LINHA POR DIA DO ATENDIMENTO
despesas_df = _read_df(ABA_DESPESAS)
despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)
for c in COLS_DESPESAS_FIX:
    if c not in despesas_df.columns:
        despesas_df[c] = ""

# Junta os itens pagáveis (semana + fiados) com Data do serviço, Competência e valor da comissão
pagaveis = []
for df_part in [semana_grid, fiados_grid]:
    if df_part is None or df_part.empty:
        continue
    # df_part precisa conter as colunas "Data" (do atendimento), "Competência" e "ComissaoValor"
    pagaveis.append(df_part[["Data", "Competência", "ComissaoValor"]].copy())

if pagaveis:
    pagos = pd.concat(pagaveis, ignore_index=True)
    # normaliza data (permite formatos 12/08/2025 etc.)
    def _norm_dt(s):
        s = (s or "").strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
        return None

    pagos["_dt"] = pagos["Data"].apply(_norm_dt)
    # descarta eventuais linhas sem data válida
    pagos = pagos[pagos["_dt"].notna()].copy()

    # soma por DIA do atendimento
    por_dia = pagos.groupby(["Data", "Competência"], dropna=False)["ComissaoValor"].sum().reset_index()

    linhas = []
    terca_str = to_br_date(terca_pagto)
    for _, row in por_dia.iterrows():
        data_serv = str(row["Data"]).strip()            # dd/mm/aaaa do atendimento
        comp      = str(row["Competência"]).strip()     # mm/aaaa
        val       = float(row["ComissaoValor"])

        linhas.append({
            "Data": data_serv,  # ✅ Data do atendimento (para seu relatório)
            "Prestador": "Vinicius",
            # deixa explícito mês de competência e quando foi pago
            "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {terca_str}",
            "Valor": f'R$ {val:.2f}'.replace(".", ","),
            "Me Pag:": meio_pag
        })

    despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
    # Mantém a ordem
    colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                     [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
    despesas_final = despesas_final[colunas_finais]
    _write_df(ABA_DESPESAS, despesas_final)

    st.success(
        f"🎉 Comissão registrada! {len(linhas)} linha(s) adicionada(s) em **{ABA_DESPESAS}** "
        f"(uma por DIA do atendimento) e {len(novos_cache)} itens marcados no **{ABA_COMISSOES_CACHE}**."
    )
    st.balloons()
else:
    st.warning("Não há valores a lançar em Despesas.")
