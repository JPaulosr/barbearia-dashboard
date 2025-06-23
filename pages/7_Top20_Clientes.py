import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Top 20 Clientes", layout="wide")
st.title("🏆 Top 20 Clientes - Geral")

# Upload
arquivo = st.file_uploader("Envie a planilha Modelo_Barbearia_Automatizado.xlsx", type="xlsx")

if arquivo:
    df = pd.read_excel(arquivo, sheet_name=None)
    abas = list(df.keys())

    if "Base de Dados" in abas:
        df = df["Base de Dados"].copy()

        # Normaliza colunas
        df.columns = [str(col).strip() for col in df.columns]

        # Remove nomes genéricos
        nomes_ignorados = ["boliviano", "brasileiro", "menino"]
        def limpar_nome(nome):
            nome = str(nome).lower()
            for termo in nomes_ignorados:
                if termo in nome:
                    return None
            return nome.strip()

        df['Cliente'] = df['Cliente'].apply(limpar_nome)
        df = df.dropna(subset=['Cliente'])

        # Conversões
        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        df = df.dropna(subset=['Data'])
        df['Ano'] = df['Data'].dt.year
        df['Mês'] = df['Data'].dt.to_period("M").astype(str)

        # Filtro por ano e funcionário
        anos = sorted(df['Ano'].dropna().unique(), reverse=True)
        ano_sel = st.selectbox("📅 Filtrar por ano", anos, index=0)
        funcionarios = sorted(df['Funcionário'].dropna().unique())
        func_sel = st.multiselect("👤 Filtrar por funcionário", funcionarios, default=funcionarios)

        df_filtrado = df[(df['Ano'] == ano_sel) & (df['Funcionário'].isin(func_sel))]

        # Agrupamento por Cliente + Data para identificar atendimentos únicos
        atendimentos = df_filtrado.groupby(['Cliente', 'Data']).agg({
            'Valor': 'sum',
            'Serviço': 'count',
            'Combo': lambda x: x.notna().sum(),
            'Tipo': list
        }).reset_index()

        # Agrupamento final por cliente
        resumo = atendimentos.groupby('Cliente').agg(
            Qtd_Atendimentos=('Data', 'count'),
            Qtd_Servicos=('Serviço', 'sum'),
            Qtd_Combo=('Combo', 'sum'),
            Valor_Total=('Valor', 'sum')
        ).reset_index()

        # Simples = total de atendimentos - combos
        resumo['Qtd_Simples'] = resumo['Qtd_Atendimentos'] - resumo['Qtd_Combo']
        resumo['Valor_Formatado'] = resumo['Valor_Total'].apply(lambda x: f"R$ {x:,.2f}".replace('.', ',').replace(',', '.', 1))

        # Colunas por mês
        tabela_mensal = df_filtrado.groupby(['Cliente', 'Mês'])['Valor'].sum().unstack(fill_value=0)
        tabela_mensal = tabela_mensal.applymap(lambda x: round(x, 2))

        # Merge final
        tabela_final = resumo.merge(tabela_mensal, on='Cliente', how='left')
        tabela_final = tabela_final.sort_values(by='Valor_Total', ascending=False).head(20).reset_index(drop=True)
        tabela_final.index += 1
        tabela_final.insert(0, 'Posição', tabela_final.index)

        # Exibe
        st.dataframe(tabela_final, use_container_width=True)

        # Gráfico
        fig = px.bar(tabela_final, x='Cliente', y='Valor_Total', text='Valor_Formatado',
                     title='Top 10 Clientes por Receita', template='plotly_dark')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aba 'Base de Dados' não encontrada na planilha.")
else:
    st.info("📁 Envie o arquivo Excel para visualizar o ranking.")
