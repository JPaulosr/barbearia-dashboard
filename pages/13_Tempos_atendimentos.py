combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída", "Cliente", "Data", "Funcionário", "Tipo"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x)))
}).reset_index()

combo_grouped = pd.merge(combo_grouped, df[["Cliente", "Data", "Combo"]], on=["Cliente", "Data"], how="left")

# Calcula duração ANTES de converter para string
def calcular_duracao(row):
    try:
        inicio = row["Hora Início"]
        fim_raw = row["Hora Saída do Salão"] if pd.notnull(row["Hora Saída do Salão"]) else row["Hora Saída"]
        fim = fim_raw
        return (fim - inicio).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60
combo_grouped["Categoria"] = combo_grouped["Combo"].apply(lambda x: "Combo" if pd.notnull(x) and "+" in str(x) else "Simples")
combo_grouped["Hora Início dt"] = combo_grouped["Hora Início"]
combo_grouped["Período do Dia"] = combo_grouped["Hora Início dt"].dt.hour.apply(lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite")

# Conversão para string apenas para exibição visual (após os cálculos)
combo_grouped["Data"] = pd.to_datetime(combo_grouped["Data"]).dt.strftime("%d/%m/%Y")
combo_grouped["Hora Chegada"] = combo_grouped["Hora Chegada"].dt.strftime("%H:%M")
combo_grouped["Hora Início"] = combo_grouped["Hora Início"].dt.strftime("%H:%M")
combo_grouped["Hora Saída"] = combo_grouped["Hora Saída"].dt.strftime("%H:%M")
combo_grouped["Hora Saída do Salão"] = combo_grouped["Hora Saída do Salão"].dt.strftime("%H:%M")

# df_tempo final usado nos gráficos e tabelas
df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()
