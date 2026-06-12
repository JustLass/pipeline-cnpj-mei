"""
pages/visao_geral.py
--------------------
Página 1: Visão Geral — KPIs macro e distribuições principais.
"""

import streamlit as st

from data_loader import (
    get_kpis_gerais,
    get_distribuicao_situacao,
    get_top_cnaes,
)
from components.kpi_cards import render_kpi_row, formatar_numero, formatar_moeda, formatar_percentual
from components.charts import bar_horizontal, bar_vertical


def render():
    st.header("📊 Visão Geral")
    st.caption("Panorama macro dos Microempreendedores Individuais (MEI) no Brasil")

    # --- KPIs ---
    with st.spinner("Calculando métricas..."):
        kpis = get_kpis_gerais()

    render_kpi_row([
        {"label": "Total de MEIs", "valor": formatar_numero(kpis["total"]), "icone": "🏢"},
        {"label": "MEIs Ativos", "valor": formatar_numero(kpis["ativos"]), "icone": "✅"},
        {"label": "Taxa de Atividade", "valor": formatar_percentual(kpis["taxa_atividade"]), "icone": "📈"},
    ])

    render_kpi_row([
        {"label": "Média Capital Social", "valor": formatar_moeda(kpis["media_capital"] or 0), "icone": "💰"},
        {"label": "Mediana Capital Social", "valor": formatar_moeda(kpis["mediana_capital"] or 0), "icone": "📊"},
        {"label": "UFs Representadas", "valor": str(kpis["total_ufs"]), "icone": "🗺️"},
    ])

    st.divider()

    # --- Gráficos ---
    with st.spinner("Carregando..."):
        df_sit = get_distribuicao_situacao()
    fig = bar_vertical(
        df_sit, x="situacao_desc", y="total",
        title="Distribuição por Situação Cadastral",
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Top CNAEs ---
    st.subheader("🏭 Top 10 Atividades Econômicas (CNAE)")
    with st.spinner("Carregando..."):
        df_cnaes = get_top_cnaes(10)

    # Truncar descrições longas para o gráfico
    df_display = df_cnaes.with_columns(
        pl.when(pl.col("descricao").str.len_chars() > 50)
        .then(pl.col("descricao").str.slice(0, 47) + "...")
        .otherwise(pl.col("descricao"))
        .alias("descricao_curta")
    )

    fig = bar_horizontal(
        df_display, x="total", y="descricao_curta",
        title="",
    )
    fig.update_layout(height=450, yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


# Importação necessária para o truncamento de strings
import polars as pl
