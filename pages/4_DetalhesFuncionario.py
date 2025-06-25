import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO

st.set_page_config(layout="wide")
st.title("\U0001F9D1\u200d\U0001F4BC Detalhes do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("\U0001F4C5 Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("\U0001F4CB Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

# === Filtro por tipo de serviço ===
tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# === Histórico de atendimentos ===
st.subheader("\U0001F4C5 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

df_func["MesNum"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["MesNum"].map(meses_pt) + df_func["Data"].dt.strftime(" %Y")
receita_jp = df_func.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("MesNum")

if funcionario_escolhido.lower() == "jpaulo":
    if ano_escolhido == 2025:
        df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
        df_vini["MesNum"] = df_vini["Data"].dt.month
        df_vini["MesNome"] = df_vini["MesNum"].map(meses_pt) + df_vini["Data"].dt.strftime(" %Y")
        receita_vini = df_vini.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="Vinicius")

        receita_merged = pd.merge(receita_jp, receita_vini, on=["MesNum", "MesNome"], how="left")
        receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Vinicius"].fillna(0) * 0.5

        receita_melt = receita_merged.melt(id_vars=["MesNum", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                           var_name="Tipo", value_name="Valor")
        receita_melt = receita_melt.sort_values("MesNum")

        fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                                  labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
        fig_mensal_comp.update_layout(height=450, template="plotly_white")
        st.plotly_chart(fig_mensal_comp, use_container_width=True)

        # <<< ADICIONADO: Tabela detalhada com valores formatados >>>
        receita_merged["Comissão (50%) do Vinicius"] = receita_merged["Vinicius"].fillna(0) * 0.5
        receita_merged["Total (JPaulo + Comissão)"] = receita_merged["JPaulo"] + receita_merged["Comissão (50%) do Vinicius"]
        receita_merged["Comissão (50%) do Vinicius"] = receita_merged["Comissão (50%) do Vinicius"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        receita_merged["JPaulo Formatado"] = receita_merged["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        receita_merged["Total (JPaulo + Comissão)"] = receita_merged["Total (JPaulo + Comissão)"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

        tabela = receita_merged[["MesNome", "JPaulo Formatado", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]]
        tabela.columns = ["Mês", "Receita JPaulo", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]
        st.dataframe(tabela, use_container_width=True)
    else:
        receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                            labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
        fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        fig_mensal.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_mensal, use_container_width=True)
else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

# === Receita Bruta e Receita com comissão de Vinicius ===
if funcionario_escolhido.lower() == "vinicius":
    bruto = df_func["Valor"].sum()
    liquido = bruto * 0.5
    comparativo_vinicius = pd.DataFrame({
        "Tipo de Receita": ["Bruta (100%)", "Líquida (50%)"],
        "Valor": [bruto, liquido]
    })
    comparativo_vinicius["Valor Formatado"] = comparativo_vinicius["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("\U0001F4B8 Receita Bruta vs Líquida (Vinicius)")
    st.dataframe(comparativo_vinicius[["Tipo de Receita", "Valor Formatado"]], use_container_width=True)

elif funcionario_escolhido.lower() == "jpaulo":
    valor_jp = df_func["Valor"].sum()
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == ano_escolhido)]
    valor_vini_50 = df_vini["Valor"].sum() * 0.5
    receita_total = pd.DataFrame({
        "Origem": ["Receita Bruta JPaulo", "Recebido de Vinicius (50%)", "Total"],
        "Valor": [valor_jp, valor_vini_50, valor_jp + valor_vini_50]
    })
    receita_total["Valor Formatado"] = receita_total["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("\U0001F4B0 Receita JPaulo: Própria + Comissão do Vinicius")
    st.dataframe(receita_total[["Origem", "Valor Formatado"]], use_container_width=True)

# === Ticket Médio por Mês (registros antes da data, agrupado após) ===
st.subheader("\U0001F4C9 Ticket Médio por Mês")
data_referencia = pd.to_datetime("2025-05-11")
df_func["Grupo"] = df_func["Data"].dt.strftime("%Y-%m-%d") + "_" + df_func["Cliente"]
antes_ticket = df_func[df_func["Data"] < data_referencia].copy()
antes_ticket["AnoMes"] = antes_ticket["Data"].dt.to_period("M").astype(str)
antes_ticket = antes_ticket.groupby(["AnoMes"])["Valor"].mean().reset_index(name="Ticket Médio")

depois_ticket = df_func[df_func["Data"] >= data_referencia].copy()
depois_ticket = depois_ticket.groupby(["Grupo", "Data"])["Valor"].sum().reset_index()
depois_ticket["AnoMes"] = depois_ticket["Data"].dt.to_period("M").astype(str)
depois_ticket = depois_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

ticket_mensal = pd.concat([antes_ticket, depois_ticket]).groupby("AnoMes")["Ticket Médio"].mean().reset_index()
ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(ticket_mensal, use_container_width=True)

# === Exportar dados ===
st.subheader("\U0001F4E5 Exportar dados filtrados")
buffer = BytesIO()
df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
st.download_button("Baixar Excel com dados filtrados", data=buffer.getvalue(), file_name="dados_filtrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
