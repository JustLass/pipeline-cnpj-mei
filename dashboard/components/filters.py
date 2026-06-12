"""
components/filters.py
---------------------
Componentes de filtro reutilizáveis para a sidebar.
"""

import streamlit as st
import polars as pl

from config import SITUACAO_CADASTRAL, PORTE_EMPRESA, UFS_BRASIL


def filtro_uf(key: str = "filtro_uf") -> list[str]:
    """Multiselect de UFs do Brasil."""
    return st.multiselect(
        "🗺️ Estado (UF)",
        options=UFS_BRASIL,
        default=[],
        key=key,
        placeholder="Todos os estados",
    )


def filtro_situacao(key: str = "filtro_situacao") -> list[int]:
    """Multiselect de situações cadastrais."""
    opcoes = {v: k for k, v in SITUACAO_CADASTRAL.items()}
    selecionados = st.multiselect(
        "📋 Situação Cadastral",
        options=list(opcoes.keys()),
        default=[],
        key=key,
        placeholder="Todas as situações",
    )
    return [opcoes[s] for s in selecionados]


def filtro_porte(key: str = "filtro_porte") -> list[int]:
    """Multiselect de portes de empresa."""
    opcoes = {v: k for k, v in PORTE_EMPRESA.items()}
    selecionados = st.multiselect(
        "🏢 Porte da Empresa",
        options=list(opcoes.keys()),
        default=[],
        key=key,
        placeholder="Todos os portes",
    )
    return [opcoes[s] for s in selecionados]


def filtro_ano(key: str = "filtro_ano", min_ano: int = 2000, max_ano: int = 2025) -> tuple[int, int]:
    """Slider de range de anos."""
    return st.slider(
        "📅 Período (Ano de Abertura)",
        min_value=min_ano,
        max_value=max_ano,
        value=(min_ano, max_ano),
        key=key,
    )


def filtro_cnae_select(dim_cnaes: pl.DataFrame, key: str = "filtro_cnae") -> int | None:
    """Selectbox de CNAE com busca por descrição."""
    opcoes_df = dim_cnaes.sort("descricao")
    opcoes = {
        f"{row['codigo']} - {row['descricao']}": row["codigo"]
        for row in opcoes_df.iter_rows(named=True)
    }
    selecionado = st.selectbox(
        "🏭 Atividade Econômica (CNAE)",
        options=["Todos"] + list(opcoes.keys()),
        key=key,
    )
    if selecionado == "Todos":
        return None
    return opcoes[selecionado]
