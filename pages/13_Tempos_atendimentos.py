# Agrupamento mantendo os horários como datetime para cálculos corretos
combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída", "Cliente", "Data", "Funcionário", "Tipo"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x)))
}).reset_index()

# Juntar info do combo
combo_grouped = pd.merge(combo_grouped, df[["Cliente", "Data", "Combo"]], on=["Cliente", "Data"], how="left")

# Calcular duração correta mantendo datetime
def calcular_duracao(row):
    try:
        inicio = row["Hora Início"]
        fim = row["Hora Saída do Salão"] if pd.notnull(row["Hora Saída do Salão"]) else row["Hora Saída"]
        return (fim - inicio).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(
    lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else ""
)

# Calcular espera
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60
combo_grouped["Categoria"] = combo_grouped["Combo"].apply(lambda x: "Combo" if pd.notnull(x) and "+" in str(x) else "Simples")

# Para período do dia (baseado na hora de início)
combo_grouped["Hora Início dt"] = combo_grouped["Hora Início"]
combo_grouped["Período do Dia"] = combo_grouped["Hora Início"].dt.hour.apply(
    lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite"
)

# Formatação para exibição (apenas após os cálculos)
combo_grouped["Data"] = pd.to_datetime(combo_grouped["Data"]).dt.strftime("%d/%m/%Y")
combo_grouped["Hora Chegada"] = combo_grouped["Hora Chegada"].dt.strftime("%H:%M")
combo_grouped["Hora Início"] = combo_grouped["Hora Início"].dt.strftime("%H:%M")
combo_grouped["Hora Saída"] = combo_grouped["Hora Saída"].dt.strftime("%H:%M")
combo_grouped["Hora Saída do Salão"] = combo_grouped["Hora Saída do Salão"].dt.strftime("%H:%M")

# Dados finais com tempo válido
df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()
