"""
pages/analise_temporal.py
-------------------------
Página 2: Análise Temporal — Séries temporais de abertura e fechamento de MEIs.
"""

import streamlit as st
import polars as pl

from data_loader import (
    get_consolidado_anual,
)
from components.charts import line_chart_multi
from components.kpi_cards import formatar_numero
from components.filters import filtro_ano


def render():
    st.header("📈 Análise Temporal")
    st.caption("Evolução de abertura e fechamento de MEIs ao longo do tempo")

    # --- Filtro de período ---
    with st.sidebar:
        st.subheader("📅 Filtros Temporais")
        # MEI oficialmente começou em 2009
        ano_min, ano_max = filtro_ano(key="temporal_ano", min_ano=2009, max_ano=2025)

    # --- Abertura e Fechamento por Ano ---
    st.subheader("Evolução Anual: Aberturas vs Fechamentos")

    with st.spinner("Processando série anual..."):
        df_ano = get_consolidado_anual()

    # Aplicar filtro de período
    df_ano_filtrado = df_ano.filter(
        (pl.col("ano") >= ano_min) & (pl.col("ano") <= ano_max)
    )

    if len(df_ano_filtrado) > 0:
        # KPIs do período
        total_aberturas = df_ano_filtrado["aberturas"].sum()
        total_fechamentos = df_ano_filtrado["fechamentos"].sum()
        saldo = total_aberturas - total_fechamentos

        col1, col2, col3 = st.columns(3)
        col1.metric("📊 Total Aberturas", formatar_numero(total_aberturas))
        col2.metric("❌ Total Fechamentos", formatar_numero(total_fechamentos))
        col3.metric(
            "📈 Saldo Líquido",
            formatar_numero(saldo),
            delta=formatar_numero(saldo),
            delta_color="normal" if saldo >= 0 else "inverse"
        )

        # Reformatar dados para o formato aceito por line_chart_multi
        df_anual_melted = df_ano_filtrado.unpivot(
            index=["ano"],
            on=["aberturas", "fechamentos"],
            variable_name="tipo",
            value_name="quantidade"
        ).with_columns(
            pl.col("tipo").replace({
                "aberturas": "Aberturas",
                "fechamentos": "Fechamentos"
            })
        )

        fig = line_chart_multi(
            df_anual_melted,
            x="ano", y="quantidade", color="tipo",
            title=f"Evolução Anual de Empresas MEI ({ano_min}–{ano_max})",
        )
        fig.update_layout(
            height=450,
            xaxis_title="Ano",
            yaxis_title="Quantidade de Empresas",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Nenhum dado encontrado para o período selecionado.")

