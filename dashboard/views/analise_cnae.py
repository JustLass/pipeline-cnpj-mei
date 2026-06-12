"""
pages/analise_cnae.py
---------------------
Página 4: Análise por Atividade Econômica (CNAE).
"""

import streamlit as st
import polars as pl

from data_loader import (
    get_top_cnaes_detalhado,
    get_evolucao_top_cnaes,
)
from components.charts import bar_horizontal, line_chart_multi
from components.kpi_cards import formatar_numero, formatar_percentual


def render():
    st.header("🏭 Análise por Atividade Econômica")
    st.caption("Distribuição dos MEIs por CNAE (Classificação Nacional de Atividades Econômicas)")

    # --- Top 20 CNAEs ---
    st.subheader("Top 20 Atividades Econômicas")
    with st.spinner("Carregando dados por CNAE..."):
        df_cnaes = get_top_cnaes_detalhado(20)

    if len(df_cnaes) > 0:
        # KPIs do CNAE mais popular
        top = df_cnaes.row(0, named=True)
        total_geral = df_cnaes["total"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("🏆 CNAE Mais Popular", top["descricao"][:40] + "..." if len(top["descricao"]) > 40 else top["descricao"])
        col2.metric("📊 MEIs Nessa Atividade", formatar_numero(top["total"]))
        col3.metric("📈 % do Top 20", formatar_percentual(top["total"] / total_geral * 100))

        st.divider()

        # Gráfico de barras com descrições truncadas
        df_display = df_cnaes.with_columns(
            pl.when(pl.col("descricao").str.len_chars() > 45)
            .then(pl.col("descricao").str.slice(0, 42) + "...")
            .otherwise(pl.col("descricao"))
            .alias("atividade")
        )

        fig = bar_horizontal(
            df_display, x="total", y="atividade", title="",
        )
        fig.update_layout(height=600, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        st.divider()

        # --- Análise Temporal dos Top 5 CNAEs ---
        st.subheader("📈 Evolução de Aberturas: Top 5 Atividades")
        with st.spinner("Carregando histórico das atividades..."):
            df_evolucao = get_evolucao_top_cnaes(5)
            
        if len(df_evolucao) > 0:
            fig_evol = line_chart_multi(
                df_evolucao,
                x="ano_abertura", y="total", color="cnae_desc",
                title="Abertura Anual de Empresas MEI para as Atividades do Top 5"
            )
            fig_evol.update_layout(
                height=450,
                xaxis_title="Ano de Abertura",
                yaxis_title="Quantidade de Aberturas",
            )
            st.plotly_chart(fig_evol, use_container_width=True)


