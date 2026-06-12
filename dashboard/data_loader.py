"""
data_loader.py
--------------
Funções de carga e transformação dos Parquets Gold usando Polars.
Todas as funções de leitura usam @st.cache_data para evitar releituras.
"""

import streamlit as st
import polars as pl

from config import (
    CAMINHO_FATO, DIM_CNAES, DIM_MOTIVOS, DIM_MUNICIPIOS,
    DIM_NATUREZAS, DIM_PAISES, DIM_QUALIFICACOES,
    SITUACAO_CADASTRAL, PORTE_EMPRESA,
)


# ---------------------------------------------------------------------------
# DIMENSÕES (pequenas, carregadas 1x na RAM)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def carregar_dim_cnaes() -> pl.DataFrame:
    return pl.read_parquet(DIM_CNAES)


@st.cache_data(ttl=3600)
def carregar_dim_motivos() -> pl.DataFrame:
    return pl.read_parquet(DIM_MOTIVOS)


@st.cache_data(ttl=3600)
def carregar_dim_municipios() -> pl.DataFrame:
    return pl.read_parquet(DIM_MUNICIPIOS)


@st.cache_data(ttl=3600)
def carregar_dim_naturezas() -> pl.DataFrame:
    return pl.read_parquet(DIM_NATUREZAS)


@st.cache_data(ttl=3600)
def carregar_dim_paises() -> pl.DataFrame:
    return pl.read_parquet(DIM_PAISES)


@st.cache_data(ttl=3600)
def carregar_dim_qualificacoes() -> pl.DataFrame:
    return pl.read_parquet(DIM_QUALIFICACOES)


def carregar_todas_dimensoes() -> dict[str, pl.DataFrame]:
    """Carrega todas as tabelas de dimensão de uma vez."""
    return {
        "cnaes": carregar_dim_cnaes(),
        "motivos": carregar_dim_motivos(),
        "municipios": carregar_dim_municipios(),
        "naturezas": carregar_dim_naturezas(),
        "paises": carregar_dim_paises(),
        "qualificacoes": carregar_dim_qualificacoes(),
    }


def resolver_codigo(dim_df: pl.DataFrame, codigo: int | None) -> str:
    """Resolve um código numérico para descrição usando uma tabela dimensão."""
    if codigo is None:
        return "Não informado"
    resultado = dim_df.filter(pl.col("codigo") == codigo)
    if len(resultado) > 0:
        return resultado["descricao"][0]
    return f"Código {codigo}"


# ---------------------------------------------------------------------------
# TABELA FATO — Agregações com scan_parquet (lazy, sem carregar tudo na RAM)
# ---------------------------------------------------------------------------

def _scan_fato() -> pl.LazyFrame:
    """Retorna um LazyFrame da tabela fato MEI, limitando de 2009 até 2025."""
    return pl.scan_parquet(CAMINHO_FATO).filter(
        (pl.col("data_inicio_atividade") >= 20090000) & (pl.col("data_inicio_atividade") < 20260000)
    )


def _adicionar_colunas_data(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Converte data_inicio_atividade (UInt32 YYYYMMDD) em colunas de ano e mês.
    Filtra datas inválidas (0, nulos, etc), iniciando no ano real de início do MEI (2009) até 2025.
    """
    return lf.with_columns(
        (pl.col("data_inicio_atividade") // 10000).cast(pl.UInt16).alias("ano_abertura"),
        ((pl.col("data_inicio_atividade") % 10000) // 100).cast(pl.UInt8).alias("mes_abertura"),
    ).filter(
        (pl.col("ano_abertura") >= 2009) & (pl.col("ano_abertura") <= 2025)
    )


def _adicionar_colunas_data_fechamento(lf: pl.LazyFrame) -> pl.LazyFrame:
    """
    Converte data_situacao_cadastral (UInt32 YYYYMMDD) em colunas de ano e mês de fechamento,
    filtrando apenas estabelecimentos Baixados (situacao_cadastral == 8) até 2025.
    """
    return lf.filter(
        (pl.col("situacao_cadastral") == 8) &
        (pl.col("data_situacao_cadastral").is_not_null()) &
        (pl.col("data_situacao_cadastral") > 0)
    ).with_columns(
        (pl.col("data_situacao_cadastral") // 10000).cast(pl.UInt16).alias("ano_fechamento"),
        ((pl.col("data_situacao_cadastral") % 10000) // 100).cast(pl.UInt8).alias("mes_fechamento"),
    ).filter(
        (pl.col("ano_fechamento") >= 2009) & (pl.col("ano_fechamento") <= 2025)
    )


@st.cache_data(ttl=3600)
def get_consolidado_anual() -> pl.DataFrame:
    """Combina aberturas e fechamentos de MEIs por ano."""
    df_ab = (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura")
        .agg(pl.len().alias("aberturas"))
        .rename({"ano_abertura": "ano"})
    )
    
    df_fech = (
        _adicionar_colunas_data_fechamento(_scan_fato())
        .group_by("ano_fechamento")
        .agg(pl.len().alias("fechamentos"))
        .rename({"ano_fechamento": "ano"})
    )
    
    df_comb = df_ab.join(df_fech, on="ano", how="full").collect()
    
    return df_comb.with_columns([
        pl.col("aberturas").fill_null(0),
        pl.col("fechamentos").fill_null(0),
    ]).sort("ano")


@st.cache_data(ttl=3600)
def get_consolidado_mensal() -> pl.DataFrame:
    """Combina aberturas e fechamentos de MEIs por ano e mês em uma única série temporal."""
    # Aberturas
    df_ab = (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura", "mes_abertura")
        .agg(pl.len().alias("aberturas"))
        .rename({"ano_abertura": "ano", "mes_abertura": "mes"})
    )
    
    # Fechamentos (Baixados)
    df_fech = (
        _adicionar_colunas_data_fechamento(_scan_fato())
        .group_by("ano_fechamento", "mes_fechamento")
        .agg(pl.len().alias("fechamentos"))
        .rename({"ano_fechamento": "ano", "mes_fechamento": "mes"})
    )
    
    # Outer Join para garantir que tenhamos todos os meses
    df_comb = df_ab.join(df_fech, on=["ano", "mes"], how="full").collect()
    
    # Preencher nulos com 0 e gerar a coluna de data real para o eixo X
    # Tratar os nulos resultantes do join para as chaves
    df_comb = df_comb.with_columns([
        pl.col("ano").fill_null(pl.col("ano_right")),
        pl.col("mes").fill_null(pl.col("mes_right")),
    ]).with_columns([
        pl.col("aberturas").fill_null(0),
        pl.col("fechamentos").fill_null(0),
        pl.date(pl.col("ano"), pl.col("mes"), 1).alias("data_mes")
    ]).sort("data_mes")
    
    return df_comb



@st.cache_data(ttl=3600)
def get_kpis_gerais() -> dict:
    """Calcula os KPIs principais da Visão Geral."""
    resultado = (
        _scan_fato()
        .select(
            pl.len().alias("total"),
            (pl.col("situacao_cadastral") == 2).sum().alias("ativos"),
            pl.col("capital_social").mean().alias("media_capital"),
            pl.col("capital_social").median().alias("mediana_capital"),
            pl.col("uf").n_unique().alias("total_ufs"),
        )
        .collect()
    )
    r = resultado.row(0, named=True)
    r["taxa_atividade"] = (r["ativos"] / r["total"] * 100) if r["total"] > 0 else 0
    return r


@st.cache_data(ttl=3600)
def get_distribuicao_situacao() -> pl.DataFrame:
    """Contagem de MEIs por situação cadastral."""
    df = (
        _scan_fato()
        .group_by("situacao_cadastral")
        .agg(pl.len().alias("total"))
        .sort("total", descending=True)
        .collect()
    )
    # Resolver códigos
    mapa = pl.DataFrame({
        "situacao_cadastral": list(SITUACAO_CADASTRAL.keys()),
        "situacao_desc": list(SITUACAO_CADASTRAL.values()),
    }).cast({"situacao_cadastral": pl.UInt8})
    return df.join(mapa, on="situacao_cadastral", how="left").with_columns(
        pl.col("situacao_desc").fill_null("Desconhecido")
    )


@st.cache_data(ttl=3600)
def get_distribuicao_porte() -> pl.DataFrame:
    """Contagem de MEIs por porte da empresa."""
    df = (
        _scan_fato()
        .group_by("porte_empresa")
        .agg(pl.len().alias("total"))
        .sort("total", descending=True)
        .collect()
    )
    mapa = pl.DataFrame({
        "porte_empresa": list(PORTE_EMPRESA.keys()),
        "porte_desc": list(PORTE_EMPRESA.values()),
    }).cast({"porte_empresa": pl.UInt8})
    return df.join(mapa, on="porte_empresa", how="left").with_columns(
        pl.col("porte_desc").fill_null("Desconhecido")
    )


@st.cache_data(ttl=3600)
def get_top_cnaes(n: int = 10) -> pl.DataFrame:
    """Top N CNAEs mais frequentes, com descrição."""
    df = (
        _scan_fato()
        .group_by("cnae_fiscal_principal")
        .agg(pl.len().alias("total"))
        .sort("total", descending=True)
        .head(n)
        .collect()
    )
    dim = carregar_dim_cnaes()
    return df.join(
        dim, left_on="cnae_fiscal_principal", right_on="codigo", how="left"
    ).with_columns(
        pl.col("descricao").fill_null("Sem descrição")
    )


# ---------------------------------------------------------------------------
# ANÁLISE TEMPORAL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_aberturas_por_ano() -> pl.DataFrame:
    """Abertura de MEIs agrupada por ano."""
    return (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura")
        .agg(pl.len().alias("total"))
        .sort("ano_abertura")
        .collect()
    )


@st.cache_data(ttl=3600)
def get_aberturas_por_mes_ano() -> pl.DataFrame:
    """Abertura de MEIs agrupada por ano e mês."""
    return (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura", "mes_abertura")
        .agg(pl.len().alias("total"))
        .sort("ano_abertura", "mes_abertura")
        .collect()
    )


@st.cache_data(ttl=3600)
def get_aberturas_por_ano_porte() -> pl.DataFrame:
    """Abertura de MEIs agrupada por ano e porte."""
    df = (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura", "porte_empresa")
        .agg(pl.len().alias("total"))
        .sort("ano_abertura")
        .collect()
    )
    mapa = pl.DataFrame({
        "porte_empresa": list(PORTE_EMPRESA.keys()),
        "porte_desc": list(PORTE_EMPRESA.values()),
    }).cast({"porte_empresa": pl.UInt8})
    return df.join(mapa, on="porte_empresa", how="left").with_columns(
        pl.col("porte_desc").fill_null("Desconhecido")
    )


@st.cache_data(ttl=3600)
def get_capital_medio_por_ano() -> pl.DataFrame:
    """Média de capital social por ano de abertura."""
    return (
        _adicionar_colunas_data(_scan_fato())
        .group_by("ano_abertura")
        .agg(pl.col("capital_social").mean().alias("media_capital"))
        .sort("ano_abertura")
        .collect()
    )


# ---------------------------------------------------------------------------
# ANÁLISE GEOGRÁFICA
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_meis_por_uf() -> pl.DataFrame:
    """Contagem de MEIs por UF."""
    return (
        _scan_fato()
        .group_by("uf")
        .agg(
            pl.len().alias("total"),
            (pl.col("situacao_cadastral") == 2).sum().alias("ativos"),
            pl.col("capital_social").mean().alias("media_capital"),
        )
        .sort("total", descending=True)
        .collect()
    ).with_columns(
        (pl.col("ativos") / pl.col("total") * 100).round(1).alias("pct_ativos")
    )


@st.cache_data(ttl=3600)
def get_top_municipios(n: int = 15) -> pl.DataFrame:
    """Top N municípios com mais MEIs, com descrição."""
    df = (
        _scan_fato()
        .group_by("municipio")
        .agg(pl.len().alias("total"))
        .sort("total", descending=True)
        .head(n)
        .collect()
    )
    dim = carregar_dim_municipios()
    return df.join(
        dim, left_on="municipio", right_on="codigo", how="left"
    ).with_columns(
        pl.col("descricao").fill_null("Não informado")
    )


@st.cache_data(ttl=3600)
def get_meis_por_uf_municipio_top(top_municipios: int = 5) -> pl.DataFrame:
    """Top municípios por UF para treemap."""
    df = (
        _scan_fato()
        .group_by("uf", "municipio")
        .agg(pl.len().alias("total"))
        .collect()
    )
    # Pegar top N municípios por UF
    df = df.sort("total", descending=True).group_by("uf").head(top_municipios)
    dim = carregar_dim_municipios()
    return df.join(
        dim, left_on="municipio", right_on="codigo", how="left"
    ).with_columns(
        pl.col("descricao").fill_null("Não informado")
    ).sort("uf", "total", descending=[False, True])


# ---------------------------------------------------------------------------
# ANÁLISE POR CNAE
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_top_cnaes_detalhado(n: int = 20) -> pl.DataFrame:
    """Top N CNAEs com métricas detalhadas."""
    df = (
        _scan_fato()
        .group_by("cnae_fiscal_principal")
        .agg(
            pl.len().alias("total"),
            (pl.col("situacao_cadastral") == 2).sum().alias("ativos"),
            pl.col("capital_social").mean().alias("media_capital"),
        )
        .sort("total", descending=True)
        .head(n)
        .collect()
    ).with_columns(
        (pl.col("ativos") / pl.col("total") * 100).round(1).alias("pct_ativos")
    )
    dim = carregar_dim_cnaes()
    return df.join(
        dim, left_on="cnae_fiscal_principal", right_on="codigo", how="left"
    ).with_columns(
        pl.col("descricao").fill_null("Sem descrição")
    )


@st.cache_data(ttl=3600)
def get_cnae_por_situacao(n: int = 10) -> pl.DataFrame:
    """Top N CNAEs × situação cadastral."""
    # Primeiro pegar os top N CNAEs
    top = (
        _scan_fato()
        .group_by("cnae_fiscal_principal")
        .agg(pl.len().alias("total_geral"))
        .sort("total_geral", descending=True)
        .head(n)
        .select("cnae_fiscal_principal")
        .collect()
    )

    df = (
        _scan_fato()
        .filter(pl.col("cnae_fiscal_principal").is_in(top["cnae_fiscal_principal"]))
        .group_by("cnae_fiscal_principal", "situacao_cadastral")
        .agg(pl.len().alias("total"))
        .collect()
    )
    # Resolver descrições
    dim_cnae = carregar_dim_cnaes()
    mapa_sit = pl.DataFrame({
        "situacao_cadastral": list(SITUACAO_CADASTRAL.keys()),
        "situacao_desc": list(SITUACAO_CADASTRAL.values()),
    }).cast({"situacao_cadastral": pl.UInt8})

    return (
        df.join(dim_cnae, left_on="cnae_fiscal_principal", right_on="codigo", how="left")
        .join(mapa_sit, on="situacao_cadastral", how="left")
        .with_columns(
            pl.col("descricao").fill_null("Sem descrição"),
            pl.col("situacao_desc").fill_null("Desconhecido"),
        )
    )


@st.cache_data(ttl=3600)
def get_cnae_secao_sunburst() -> pl.DataFrame:
    """Dados para sunburst: seção CNAE (2 primeiros dígitos) → atividade."""
    df = (
        _scan_fato()
        .group_by("cnae_fiscal_principal")
        .agg(pl.len().alias("total"))
        .collect()
    )
    dim = carregar_dim_cnaes()
    df = df.join(dim, left_on="cnae_fiscal_principal", right_on="codigo", how="left")

    # Extrair divisão CNAE (2 primeiros dígitos)
    return df.with_columns(
        (pl.col("cnae_fiscal_principal") // 100000).cast(pl.UInt8).alias("divisao_cnae"),
        pl.col("descricao").fill_null("Sem descrição"),
    ).sort("total", descending=True)


@st.cache_data(ttl=3600)
def get_evolucao_top_cnaes(n: int = 5) -> pl.DataFrame:
    """Retorna a evolução anual de aberturas para as Top N atividades (CNAEs) mais comuns."""
    # 1. Identificar os Top N CNAEs
    top_cnaes = (
        _scan_fato()
        .group_by("cnae_fiscal_principal")
        .agg(pl.len().alias("total_geral"))
        .sort("total_geral", descending=True)
        .head(n)
        .select("cnae_fiscal_principal")
        .collect()
    )
    
    # 2. Obter aberturas anuais para estes top CNAEs
    df = (
        _adicionar_colunas_data(_scan_fato())
        .filter(pl.col("cnae_fiscal_principal").is_in(top_cnaes["cnae_fiscal_principal"]))
        .group_by("ano_abertura", "cnae_fiscal_principal")
        .agg(pl.len().alias("total"))
        .sort("ano_abertura")
        .collect()
    )
    
    # 3. Trazer descrições das atividades
    dim = carregar_dim_cnaes()
    df_completo = df.join(
        dim, left_on="cnae_fiscal_principal", right_on="codigo", how="left"
    ).with_columns(
        pl.col("descricao").fill_null("Sem descrição")
    )
    
    # Truncar descrições longas para melhor visualização em legendas
    return df_completo.with_columns(
        pl.when(pl.col("descricao").str.len_chars() > 30)
        .then(pl.col("descricao").str.slice(0, 27) + "...")
        .otherwise(pl.col("descricao"))
        .alias("cnae_desc")
    ).sort("ano_abertura")
