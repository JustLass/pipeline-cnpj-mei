"""
mongo_client.py
---------------
Wrapper para consultas ao MongoDB (coleção empresas_mei).
"""

import streamlit as st
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from config import MONGO_URI, MONGO_DB, MONGO_COLLECTION


@st.cache_resource
def _get_client() -> MongoClient:
    """Cria e cacheia a conexão MongoDB (resource, não serializável)."""
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)


def testar_conexao() -> bool:
    """Testa se o MongoDB está acessível."""
    try:
        client = _get_client()
        client.admin.command("ping")
        return True
    except (ConnectionFailure, Exception):
        return False


def _get_collection():
    """Retorna a coleção empresas_mei."""
    client = _get_client()
    return client[MONGO_DB][MONGO_COLLECTION]


def buscar_por_cnpj(cnpj_basico: int) -> dict | None:
    """
    Busca um documento pelo CNPJ básico (chave primária _id).
    Retorna o documento completo ou None.
    """
    return _get_collection().find_one({"_id": cnpj_basico})


def buscar_por_uf_cnae(uf: str, cnae: int | None = None, limite: int = 50) -> list[dict]:
    """
    Busca empresas por UF e opcionalmente por CNAE principal.
    Retorna lista de documentos (limitada).
    """
    filtro = {"estabelecimentos.endereco.uf": uf.upper()}
    if cnae is not None:
        filtro["estabelecimentos.cnae_fiscal_principal"] = cnae
    return list(
        _get_collection()
        .find(filtro)
        .limit(limite)
    )


def contar_por_uf() -> list[dict]:
    """
    Aggregation pipeline: contagem de documentos por UF.
    Usa $unwind nos estabelecimentos para pegar a UF de cada um.
    """
    pipeline = [
        {"$unwind": "$estabelecimentos"},
        {"$group": {
            "_id": "$estabelecimentos.endereco.uf",
            "total": {"$sum": 1},
        }},
        {"$sort": {"total": -1}},
    ]
    return list(_get_collection().aggregate(pipeline))


def stats_collection() -> dict:
    """Retorna estatísticas básicas da coleção."""
    col = _get_collection()
    return {
        "total_documentos": col.estimated_document_count(),
        "nome": MONGO_COLLECTION,
        "banco": MONGO_DB,
    }
