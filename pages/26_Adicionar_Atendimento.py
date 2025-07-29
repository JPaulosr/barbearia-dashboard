valores_referencia = (
    df_base[df_base["Valor"].notna() & df_base["Valor"].astype(str).str.startswith("R$")]
    .assign(valor_num=lambda d: pd.to_numeric(
        d["Valor"].astype(str)
        .str.replace("R\$", "", regex=True)
        .str.replace(",", "."), errors="coerce"
    ))
    .dropna(subset=["valor_num"])
    .groupby("Serviço")["valor_num"]
    .mean()
    .round(2)
    .to_dict()
)
