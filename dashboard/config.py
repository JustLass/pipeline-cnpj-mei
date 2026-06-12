"""
config.py
---------
Caminhos, constantes e mapeamentos para o dashboard MEI.
"""

import os

# ---------------------------------------------------------------------------
# CAMINHOS (relativos à raiz do projeto Pipeline CNPJ RF)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PASTA_GOLD = os.path.join(_PROJECT_ROOT, "data", "parquets")
CAMINHO_FATO = os.path.join(PASTA_GOLD, "mei_estabelecimentos_*.parquet")

# Dimensões
DIM_CNAES = os.path.join(PASTA_GOLD, "dim_cnaes.parquet")
DIM_MOTIVOS = os.path.join(PASTA_GOLD, "dim_motivos_situacao.parquet")
DIM_MUNICIPIOS = os.path.join(PASTA_GOLD, "dim_municipios.parquet")
DIM_NATUREZAS = os.path.join(PASTA_GOLD, "dim_naturezas_juridicas.parquet")
DIM_PAISES = os.path.join(PASTA_GOLD, "dim_paises.parquet")
DIM_QUALIFICACOES = os.path.join(PASTA_GOLD, "dim_qualificacoes_socios.parquet")

# ---------------------------------------------------------------------------
# MONGODB
# ---------------------------------------------------------------------------
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "cnpj_rf"
MONGO_COLLECTION = "empresas_mei"

# ---------------------------------------------------------------------------
# MAPEAMENTOS FIXOS (não estão em tabelas dimensão)
# ---------------------------------------------------------------------------

SITUACAO_CADASTRAL = {
    1: "Nula",
    2: "Ativa",
    3: "Suspensa",
    4: "Inapta",
    8: "Baixada",
}

PORTE_EMPRESA = {
    0: "Não Informado",
    1: "Micro Empresa",
    3: "Empresa de Pequeno Porte",
    5: "Demais",
}

IDENTIFICADOR_MATRIZ_FILIAL = {
    1: "Matriz",
    2: "Filial",
}

# ---------------------------------------------------------------------------
# CORES DO DASHBOARD (paleta premium)
# ---------------------------------------------------------------------------

CORES = {
    "primaria":     "#6366F1",   # Indigo
    "secundaria":   "#8B5CF6",   # Violet
    "sucesso":      "#10B981",   # Emerald
    "alerta":       "#F59E0B",   # Amber
    "erro":         "#EF4444",   # Red
    "info":         "#3B82F6",   # Blue
    "fundo":        "#0F172A",   # Slate 900
    "card":         "#1E293B",   # Slate 800
    "texto":        "#F8FAFC",   # Slate 50
    "texto_sec":    "#94A3B8",   # Slate 400
    "borda":        "#334155",   # Slate 700
}

PALETA_SEQUENCIAL = [
    "#6366F1", "#818CF8", "#A5B4FC",
    "#8B5CF6", "#A78BFA", "#C4B5FD",
    "#3B82F6", "#60A5FA", "#93C5FD",
    "#10B981", "#34D399", "#6EE7B7",
]

PALETA_SITUACAO = {
    "Ativa":    "#10B981",
    "Baixada":  "#EF4444",
    "Inapta":   "#F59E0B",
    "Suspensa": "#F97316",
    "Nula":     "#64748B",
}

# ---------------------------------------------------------------------------
# UFs do Brasil (para o mapa choropleth)
# ---------------------------------------------------------------------------

UFS_BRASIL = [
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA",
    "MG", "MS", "MT", "PA", "PB", "PE", "PI", "PR", "RJ", "RN",
    "RO", "RR", "RS", "SC", "SE", "SP", "TO",
]
