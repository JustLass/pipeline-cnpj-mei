"""
pages/analise_geografica.py
---------------------------
Página 3: Análise Geográfica — Mapas, rankings por UF e Município.
"""

import streamlit as st
import polars as pl

from data_loader import get_meis_por_uf, get_top_municipios
from components.charts import choropleth_brasil, bar_horizontal
from components.kpi_cards import formatar_numero, formatar_moeda, formatar_percentual


def render():
    st.header("🗺️ Análise Geográfica")
    st.caption("Distribuição territorial dos MEIs por Estado e Município")

    # --- MEIs por UF ---
    with st.spinner("Carregando dados por UF..."):
        df_uf = get_meis_por_uf()

    # KPIs geográficos
    if len(df_uf) > 0:
        top_uf = df_uf.row(0, named=True)
        total_geral = df_uf["total"].sum()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("🏆 UF com Mais MEIs", top_uf["uf"])
        col2.metric("📊 Total no Topo", formatar_numero(top_uf["total"]))
        col3.metric(
            "📈 Concentração no Topo",
            formatar_percentual(top_uf["total"] / total_geral * 100),
        )
        col4.metric("🗺️ Total de UFs", str(len(df_uf)))

    st.divider()

    # --- Mapa / Ranking UF ---
    st.subheader("Ranking de MEIs por Estado")
    fig = choropleth_brasil(df_uf, locations="uf", values="total", title="")
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # --- Top Municípios ---
    st.subheader("🏙️ Top 15 Municípios com Mais MEIs")
    with st.spinner("Carregando dados municipais..."):
        df_mun = get_top_municipios(15)

    if len(df_mun) > 0:
        # Truncar nomes longos
        df_display = df_mun.with_columns(
            pl.when(pl.col("descricao").str.len_chars() > 35)
            .then(pl.col("descricao").str.slice(0, 32) + "...")
            .otherwise(pl.col("descricao"))
            .alias("municipio_nome")
        )

        fig = bar_horizontal(
            df_display, x="total", y="municipio_nome", title="",
        )
        fig.update_layout(height=500, yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
