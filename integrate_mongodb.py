"""
integrate_mongodb.py
--------------------
Script para ler a tabela fato Gold (Parquet) de MEIs, estruturar os dados
no formato de documentos BSON (aninhados) e importá-los em batches no MongoDB local.

Requisitos:
  pip install pymongo pyarrow polars
"""

import os
import sys
import gc
import glob
import time

# Auto-instalação de dependências ausentes
def instalar_dependencias():
    dependencias = []
    try:
        import pymongo
    except ImportError:
        dependencias.append("pymongo")
    try:
        import pyarrow
    except ImportError:
        dependencias.append("pyarrow")
    try:
        import polars
    except ImportError:
        dependencias.append("polars")

    if dependencias:
        print(f"📦 Instalando dependências ausentes: {', '.join(dependencias)}...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", *dependencias])
        print("✅ Dependências instaladas com sucesso!\n")

instalar_dependencias()

import polars as pl
import pyarrow.parquet as pq
from pymongo import MongoClient, ASCENDING, UpdateOne

# Configurações do MongoDB
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "cnpj_rf"
COLLECTION_NAME = "empresas_mei"

# Configurações do Dataset
PASTA_GOLD = "./data/parquets"
BATCH_SIZE = 50_000  # Tamanho do batch para leitura e inserção (ajuste conforme RAM)

def obter_caminho_gold():
    arquivos = glob.glob(os.path.join(PASTA_GOLD, "mei_estabelecimentos_*.parquet"))
    if not arquivos:
        raise FileNotFoundError(f"❌ Nenhum arquivo fato MEI encontrado em '{PASTA_GOLD}'")
    # Retorna o arquivo mais recente
    return sorted(arquivos)[-1]

def transformar_registro(r):
    """Transforma um registro plano do Parquet em um documento aninhado para o MongoDB."""
    # Tratar CNAEs secundários (String -> Array de Inteiros)
    cnae_sec_str = r.get("cnae_fiscal_secundaria")
    cnae_sec_arr = []
    if cnae_sec_str:
        try:
            cnae_sec_arr = [int(x.strip()) for x in cnae_sec_str.split(",") if x.strip()]
        except ValueError:
            pass

    # Estruturar o documento
    return {
        "_id": int(r["cnpj_basico"]),  # Usamos o cnpj_basico como chave primária única
        "razao_social": r.get("razao_social"),
        "natureza_juridica": int(r["natureza_juridica"]) if r.get("natureza_juridica") is not None else None,
        "capital_social": float(r["capital_social"]) if r.get("capital_social") is not None else 0.0,
        "porte_empresa": int(r["porte_empresa"]) if r.get("porte_empresa") is not None else None,
        "opcao_pelo_simples": "S",
        "opcao_pelo_mei": "S",
        "estabelecimentos": [
            {
                "cnpj_ordem": int(r["cnpj_ordem"]) if r.get("cnpj_ordem") is not None else None,
                "cnpj_dv": int(r["cnpj_dv"]) if r.get("cnpj_dv") is not None else None,
                "identificador_matriz_filial": int(r["identificador_matriz_filial"]) if r.get("identificador_matriz_filial") is not None else 1,
                "nome_fantasia": r.get("nome_fantasia"),
                "situacao_cadastral": int(r["situacao_cadastral"]) if r.get("situacao_cadastral") is not None else None,
                "data_situacao_cadastral": int(r["data_situacao_cadastral"]) if r.get("data_situacao_cadastral") is not None else None,
                "data_inicio_atividade": int(r["data_inicio_atividade"]) if r.get("data_inicio_atividade") is not None else None,
                "cnae_fiscal_principal": int(r["cnae_fiscal_principal"]) if r.get("cnae_fiscal_principal") is not None else None,
                "cnae_fiscal_secundarias": cnae_sec_arr,
                "endereco": {
                    "tipo_logradouro": r.get("tipo_logradouro"),
                    "logradouro": r.get("logradouro"),
                    "numero": r.get("numero"),
                    "complemento": r.get("complemento"),
                    "bairro": r.get("bairro"),
                    "cep": int(r["cep"]) if r.get("cep") is not None else None,
                    "uf": r.get("uf"),
                    "municipio": int(r["municipio"]) if r.get("municipio") is not None else None
                },
                "contato": {
                    "ddd_1": int(r["ddd_1"]) if r.get("ddd_1") is not None else None,
                    "telefone_1": r.get("telefone_1"),
                    "ddd_2": int(r["ddd_2"]) if r.get("ddd_2") is not None else None,
                    "telefone_2": r.get("telefone_2"),
                    "correio_eletronico": r.get("correio_eletronico")
                }
            }
        ]
    }

def main():
    print("🔌 Conectando ao MongoDB...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        # Testa a conexão
        client.admin.command('ping')
        print("✅ Conexão estabelecida com sucesso!")
    except Exception as e:
        print(f"❌ Erro ao conectar ao MongoDB local: {e}")
        print("Certifique-se de que o serviço do MongoDB está rodando na porta 27017.")
        sys.exit(1)

    db = client[DB_NAME]
    collection = db[COLLECTION_NAME]

    # Obter caminho do arquivo Parquet Gold
    try:
        caminho_parquet = obter_caminho_gold()
        print(f"📄 Arquivo de origem: {caminho_parquet}")
    except Exception as e:
        print(e)
        sys.exit(1)

    # Limpar coleção existente antes da importação
    print(f"🧹 Limpando coleção existente '{COLLECTION_NAME}'...")
    collection.drop()

    # Leitura e inserção por batches (PyArrow + Polars)
    print("🚀 Iniciando a importação dos dados...")
    parquet_file = pq.ParquetFile(caminho_parquet)
    total_linhas_processadas = 0
    tempo_inicio = time.time()

    # Iterar em batches sobre o arquivo parquet
    batch_num = 0
    for record_batch in parquet_file.iter_batches(batch_size=BATCH_SIZE):
        batch_num += 1
        tempo_batch_inicio = time.time()
        
        # Converte para DataFrame Polars
        df = pl.from_arrow(record_batch)
        
        # Converte para lista de dicionários nativos Python
        registros = df.to_dicts()
        
        # Transforma os registros no formato de documentos estruturados
        documentos = [transformar_registro(r) for r in registros]
        
        # Agrupa estabelecimentos pelo CNPJ Básico localmente para otimizar operações
        local_grouped = {}
        for doc in documentos:
            cnpj = doc["_id"]
            est = doc["estabelecimentos"][0]
            if cnpj not in local_grouped:
                local_grouped[cnpj] = doc
            else:
                local_grouped[cnpj]["estabelecimentos"].append(est)

        # Prepara as operações de bulk upsert
        bulk_ops = []
        for cnpj, doc in local_grouped.items():
            op = UpdateOne(
                {"_id": cnpj},
                {
                    "$setOnInsert": {
                        "razao_social": doc["razao_social"],
                        "natureza_juridica": doc["natureza_juridica"],
                        "capital_social": doc["capital_social"],
                        "porte_empresa": doc["porte_empresa"],
                        "opcao_pelo_simples": doc["opcao_pelo_simples"],
                        "opcao_pelo_mei": doc["opcao_pelo_mei"]
                    },
                    "$push": {
                        "estabelecimentos": {
                            "$each": doc["estabelecimentos"]
                        }
                    }
                },
                upsert=True
            )
            bulk_ops.append(op)

        # Execução em lote (bulk write) no MongoDB
        if bulk_ops:
            collection.bulk_write(bulk_ops, ordered=False)

        total_linhas_processadas += len(documentos)
        tempo_batch = time.time() - tempo_batch_inicio
        linhas_por_segundo = len(documentos) / tempo_batch if tempo_batch > 0 else 0
        
        print(f"   Batch {batch_num:<4} | {total_linhas_processadas:,} linhas processadas | {linhas_por_segundo:,.0f} linhas/seg")
        
        # Forçar coleta de lixo para liberar RAM
        del df, registros, documentos
        gc.collect()

    tempo_total = time.time() - tempo_inicio
    print("\n🏁 Importação finalizada!")
    print(f"   📊 Total de registros importados: {total_linhas_processadas:,}")
    print(f"   ⏳ Tempo total de processamento: {tempo_total:.1f} segundos")
    print(f"   ⚡ Média de velocidade: {total_linhas_processadas / tempo_total:,.0f} registros/segundo")

    # Criando índices analíticos
    print("\n⚡ Criando índices no MongoDB para acelerar consultas analíticas...")
    
    # Chave primária já é indexada automaticamente (_id: cnpj_basico)
    
    print("   🔍 Criando índice para cnae_fiscal_principal...")
    collection.create_index([("estabelecimentos.cnae_fiscal_principal", ASCENDING)])
    
    print("   🔍 Criando índice multikey para cnae_fiscal_secundarias...")
    collection.create_index([("estabelecimentos.cnae_fiscal_secundarias", ASCENDING)])
    
    print("   🔍 Criando índice para UF (estado)...")
    collection.create_index([("estabelecimentos.endereco.uf", ASCENDING)])
    
    print("✅ Índices criados e banco pronto para consumo!")

if __name__ == "__main__":
    main()
