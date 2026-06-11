"""
build_mei_dataset.py
--------------------
Pipeline de ingestão e transformação dos dados abertos de CNPJ da Receita Federal.

Arquitetura em camadas (Medalhão):
  BRONZE → data/extraido/   (CSVs originais, latin1, sem header — imutável)
  SILVER → data/silver/     (Parquets por arquivo, tipos corretos)
  GOLD   → data/parquets/   (Tabela fato MEI + tabelas dimensão — prontos para consumo)

Fases de execução:
  1. Dimensões : lê os 6 domínios (pequenos) → dim_*.parquet no Gold
  2. Silver    : converte cada CSV grande → Parquet, UM arquivo por vez (sem OOM)
  3. Gold      : scan_parquet lazy + filtro MEI + INNER JOIN → tabela fato
"""

import gc
import glob
import io
import os
import polars as pl
from datetime import date

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------

PASTA_BRONZE  = "./data/extraido"
PASTA_SILVER  = "./data/silver"
PASTA_GOLD    = "./data/parquets"
SNAPSHOT_DATE = date.today().strftime("%Y%m%d")
NOME_FATO     = f"mei_estabelecimentos_{SNAPSHOT_DATE}.parquet"

# Linhas por chunk na Fase 2.
# 1M linhas × 30 colunas × ~200 bytes ≈ 200 MB de texto → pico de ~400 MB de RAM por chunk.
# Reduza para 500_000 se ainda tiver pressão de memória.
CHUNK_LINHAS = 1_000_000

# ---------------------------------------------------------------------------
# SCHEMAS – tipos finais de cada coluna
# ---------------------------------------------------------------------------

SCHEMA_EMPRESAS = {
    "cnpj_basico":                 pl.UInt32,   # 8 dígitos — join key
    "razao_social":                pl.Utf8,
    "natureza_juridica":           pl.UInt16,   # código ~4 dígitos
    "qualificacao_responsavel":    pl.UInt8,    # código 2 dígitos
    "capital_social":              pl.Utf8,     # valor com vírgula decimal
    "porte_empresa":               pl.UInt8,    # 00,01,03,05
    "ente_federativo_responsavel": pl.Utf8,
}

SCHEMA_ESTABELECIMENTOS = {
    "cnpj_basico":                 pl.UInt32,
    "cnpj_ordem":                  pl.UInt16,   # 4 dígitos
    "cnpj_dv":                     pl.UInt8,    # 2 dígitos verificadores
    "identificador_matriz_filial":  pl.UInt8,   # 1=matriz, 2=filial
    "nome_fantasia":               pl.Utf8,
    "situacao_cadastral":          pl.UInt8,    # 01,02,03,04,08
    "data_situacao_cadastral":     pl.UInt32,   # YYYYMMDD
    "motivo_situacao_cadastral":   pl.UInt8,    # código 2 dígitos
    "nome_cidade_exterior":        pl.Utf8,
    "pais":                        pl.UInt16,   # código numérico
    "data_inicio_atividade":       pl.UInt32,   # YYYYMMDD — Int é 4 bytes vs 10 de String
    "cnae_fiscal_principal":       pl.UInt32,   # código CNAE 7 dígitos
    "cnae_fiscal_secundaria":      pl.Utf8,     # múltiplos CNAEs separados por vírgula
    "tipo_logradouro":             pl.Utf8,
    "logradouro":                  pl.Utf8,
    "numero":                      pl.Utf8,     # pode conter "S/N" ou letras
    "complemento":                 pl.Utf8,
    "bairro":                      pl.Utf8,
    "cep":                         pl.UInt32,   # 8 dígitos
    "uf":                          pl.Utf8,     # sigla 2 chars
    "municipio":                   pl.UInt32,   # código IBGE
    "ddd_1":                       pl.UInt16,
    "telefone_1":                  pl.Utf8,
    "ddd_2":                       pl.UInt16,
    "telefone_2":                  pl.Utf8,
    "ddd_fax":                     pl.UInt16,
    "fax":                         pl.Utf8,
    "correio_eletronico":          pl.Utf8,
    "situacao_especial":           pl.Utf8,
    "data_situacao_especial":      pl.UInt32,   # YYYYMMDD
}

SCHEMA_SIMPLES = {
    "cnpj_basico":           pl.UInt32,
    "opcao_pelo_simples":    pl.Utf8,   # S/N/branco
    "data_opcao_simples":    pl.UInt32,
    "data_exclusao_simples": pl.UInt32,
    "opcao_pelo_mei":        pl.Utf8,   # S/N/branco ← filtro principal
    "data_opcao_mei":        pl.UInt32,
    "data_exclusao_mei":     pl.UInt32,
}

SCHEMA_DOMINIO = {
    "codigo":    pl.UInt32,
    "descricao": pl.Utf8,
}

# Tabelas de domínio → nome do parquet de saída (Gold)
DOMINIOS = {
    "Naturezas":     "dim_naturezas_juridicas.parquet",
    "Qualificacoes": "dim_qualificacoes_socios.parquet",
    "Motivos":       "dim_motivos_situacao.parquet",
    "Municipios":    "dim_municipios.parquet",
    "Paises":        "dim_paises.parquet",
    "Cnaes":         "dim_cnaes.parquet",
}

# Tabelas grandes → subpasta no Silver e schema correspondente
TABELAS_SILVER = {
    "Empresas":         ("empresas",         SCHEMA_EMPRESAS),
    "Estabelecimentos": ("estabelecimentos",  SCHEMA_ESTABELECIMENTOS),
    "Simples":          ("simples",           SCHEMA_SIMPLES),
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _cast_schema_df(df: pl.DataFrame, schema: dict) -> pl.DataFrame:
    """
    Aplica cast de tipos num DataFrame já em memória.
    Strings recebem strip de espaços.
    Numéricos: branco → null → cast strict=False (erros viram null).
    """
    exprs = []
    for col, dtype in schema.items():
        if dtype == pl.Utf8:
            exprs.append(pl.col(col).str.strip_chars())
        else:
            exprs.append(
                pl.col(col)
                .str.strip_chars()
                .replace("", None)
                .cast(dtype, strict=False)
            )
    return df.with_columns(exprs)


def _listar_arquivos(pasta: str) -> list[str]:
    """Lista arquivos de uma pasta, ignorando arquivos ocultos."""
    return sorted([
        os.path.join(pasta, f)
        for f in os.listdir(pasta)
        if not f.startswith(".")
    ])


def _salvar_chunk(
    linhas: list[str],
    caminho_saida: str,
    colunas: list[str],
    schema: dict,
):
    """
    Converte uma lista de linhas CSV (já em texto Python/unicode) para um Parquet.

    O truque: juntamos as linhas em uma string, encodamos para UTF-8 em memória
    (io.BytesIO) e passamos para o pl.read_csv. Isso evita qualquer arquivo
    temporário no disco e o Polars usa seu motor nativo C para parsear.

    Custo de RAM por chunk de 1M linhas (30 colunas):
      - buffer bytes: ~200 MB
      - DataFrame strings: ~200 MB
      - Após cast de tipos: ~100 MB
      - Pico total: ~400-500 MB → seguro para 16 GB RAM
    """
    buffer = "".join(linhas).encode("utf-8")
    df = pl.read_csv(
        io.BytesIO(buffer),
        separator=";",
        has_header=False,
        new_columns=colunas,
        infer_schema_length=0,
        quote_char='"',
        ignore_errors=True,
        truncate_ragged_lines=True,
    )
    del buffer          # libera o buffer de bytes IMEDIATAMENTE antes do cast
    df = _cast_schema_df(df, schema)
    df.write_parquet(caminho_saida, compression="snappy", statistics=True)
    del df
    gc.collect()


def _csv_latin1_para_parquet(
    arq_csv: str,
    pasta_saida: str,
    nome_base: str,
    colunas: list[str],
    schema: dict,
) -> tuple[int, int]:
    """
    Lê um CSV latin1 em chunks de CHUNK_LINHAS linhas e salva múltiplos Parquets.

    Por que chunks em vez de carregar tudo?
    - scan_csv().collect() carrega o CSV INTEIRO na RAM antes de qualquer operação.
    - Para Estabelecimentos (30 colunas, ~50M linhas), isso é 10-15 GB → OOM.
    - Com chunks de 1M linhas: pico de ~400 MB de RAM, processado e descartado
      imediatamente antes de ler o próximo chunk.

    Os múltiplos Parquets gerados (nome_0000.parquet, nome_0001.parquet, ...)
    são transparentes para o scan_parquet() da Fase 3, que usa glob '*.parquet'.

    Retorna: (total_linhas, total_chunks)
    """
    total_linhas = 0
    chunk_num    = 0
    chunk: list[str] = []

    with open(arq_csv, 'r', encoding='latin1', errors='replace', buffering=8 * 1024 * 1024) as f:
        for linha in f:
            chunk.append(linha)

            if len(chunk) >= CHUNK_LINHAS:
                caminho_chunk = os.path.join(pasta_saida, f"{nome_base}_{chunk_num:04d}.parquet")
                _salvar_chunk(chunk, caminho_chunk, colunas, schema)
                total_linhas += len(chunk)
                chunk_num    += 1
                chunk         = []          # descarta as linhas da RAM
                print(f" [{chunk_num}]" , end="", flush=True)

        # Último chunk (menor que CHUNK_LINHAS)
        if chunk:
            caminho_chunk = os.path.join(pasta_saida, f"{nome_base}_{chunk_num:04d}.parquet")
            _salvar_chunk(chunk, caminho_chunk, colunas, schema)
            total_linhas += len(chunk)
            chunk_num    += 1

    return total_linhas, chunk_num


# ---------------------------------------------------------------------------
# FASE 1: DIMENSÕES → GOLD
# ---------------------------------------------------------------------------

def build_dimensoes():
    """
    Lê as 6 tabelas de domínio (pequenas, cabem em RAM) e salva como dim_*.parquet.
    Domínios usam read_csv direto pois os maiores têm ~5MB — sem risco de OOM.
    """
    os.makedirs(PASTA_GOLD, exist_ok=True)
    print("\n📚 [FASE 1] Salvando tabelas de domínio...")

    for pasta_nome, nome_parquet in DOMINIOS.items():
        pasta = os.path.join(PASTA_BRONZE, pasta_nome)
        caminho_saida = os.path.join(PASTA_GOLD, nome_parquet)

        if os.path.exists(caminho_saida):
            print(f"   ⏭️  {nome_parquet:<42} já existe — pulando")
            continue

        try:
            dfs = []
            for arq in _listar_arquivos(pasta):
                df = pl.read_csv(
                    arq,
                    separator=";",
                    encoding="latin1",
                    has_header=False,
                    new_columns=list(SCHEMA_DOMINIO.keys()),
                    infer_schema_length=0,
                    ignore_errors=True,
                )
                dfs.append(_cast_schema_df(df, SCHEMA_DOMINIO))

            df_final = pl.concat(dfs)
            df_final.write_parquet(caminho_saida, compression="snappy", statistics=True)
            tamanho_kb = os.path.getsize(caminho_saida) / 1024
            print(f"   ✅ {nome_parquet:<42} {len(df_final):>6} linhas  {tamanho_kb:>7.1f} KB")

        except Exception as e:
            print(f"   ❌ Erro em '{pasta_nome}': {e}")


# ---------------------------------------------------------------------------
# FASE 2: BRONZE → SILVER (CSV latin1 → Parquet, um arquivo por vez)
# ---------------------------------------------------------------------------

def build_silver():
    """
    Converte cada CSV das tabelas principais para chunks de Parquet na camada Silver.

    Estratégia de chunks:
      - Lê CHUNK_LINHAS linhas por vez do CSV (via Python, que aceita latin1 nativamente)
      - Cada chunk vira um Parquet separado (nome_0000.parquet, nome_0001.parquet, ...)
      - A RAM de cada chunk é liberada antes de ler o próximo
      - O scan_parquet() da Fase 3 lê todos os chunks via glob '*.parquet'

    Idempotente: se o primeiro chunk (_0000.parquet) já existir, pula o arquivo.
    """
    print("\n🥈 [FASE 2] Convertendo CSVs para Silver (chunks de 1M linhas)...")

    for pasta_nome, (subpasta, schema) in TABELAS_SILVER.items():
        pasta_entrada = os.path.join(PASTA_BRONZE, pasta_nome)
        pasta_saida   = os.path.join(PASTA_SILVER, subpasta)
        os.makedirs(pasta_saida, exist_ok=True)

        arquivos = _listar_arquivos(pasta_entrada)
        print(f"\n   📂 {pasta_nome} ({len(arquivos)} arquivo(s))...")

        for arq in arquivos:
            nome_base = os.path.splitext(os.path.basename(arq))[0]

            # Idempotência: verifica pelo primeiro chunk
            chunk_0 = os.path.join(pasta_saida, f"{nome_base}_0000.parquet")
            if os.path.exists(chunk_0):
                n_chunks = len([f for f in os.listdir(pasta_saida) if f.startswith(nome_base)])
                print(f"      ⏭️  {os.path.basename(arq):<35} já convertido ({n_chunks} chunk(s)) — pulando")
                continue

            print(f"      ⚙️  {os.path.basename(arq):<35}", end="", flush=True)
            try:
                n_linhas, n_chunks = _csv_latin1_para_parquet(
                    arq_csv=arq,
                    pasta_saida=pasta_saida,
                    nome_base=nome_base,
                    colunas=list(schema.keys()),
                    schema=schema,
                )
                print(f" ✅  {n_linhas:,} linhas → {n_chunks} chunk(s)")
            except Exception as e:
                print(f" ❌ Erro: {e}")


# ---------------------------------------------------------------------------
# FASE 3: SILVER → GOLD (Eager chunk-by-chunk JOIN + filtro MEI → tabela fato)
# ---------------------------------------------------------------------------

def build_gold():
    """
    Constrói a tabela fato MEI processando CHUNK POR CHUNK de forma EAGER.

    Por que NÃO usamos LazyFrame aqui?
    -----------------------------------------------------------------
    O Polars LazyFrame (scan_parquet + is_in + join + sink_parquet) tenta
    materializar o plano de execução inteiro na RAM antes de escrever.
    Com 70M linhas de Estabelecimentos + HashSet de 16.7M CNPJs, isso
    ultrapassa 16 GB de RAM e causa OOM ou Spill to Disk (SSD a 100%).

    Solução: Processamento EAGER chunk por chunk
    -----------------------------------------------------------------
    1. Extraímos os CNPJs MEI como um DataFrame de 1 coluna (~67 MB).
    2. Carregamos Empresas chunk por chunk, filtrando via SEMI-JOIN (~134 MB).
    3. Lemos cada Parquet de Estabelecimentos individualmente (~200 MB),
       filtramos com SEMI-JOIN, cruzamos com Empresas, escrevemos no disco
       e deletamos da RAM imediatamente.

    Pico de RAM: ~600 MB (vs 10+ GB do LazyFrame).
    SEMI-JOIN é como is_in() mas sem o DeprecationWarning e mais eficiente
    em memória (não cria um HashSet Python de 16.7M entradas).
    """
    os.makedirs(PASTA_GOLD, exist_ok=True)
    caminho_fato = os.path.join(PASTA_GOLD, NOME_FATO)

    if os.path.exists(caminho_fato):
        print(f"\n🥇 [FASE 3] Tabela fato já existe: {caminho_fato}")
        print("   Delete o arquivo e rode novamente para regerar.")
        return

    # Pasta temporária para os chunks do fato (serão consolidados no final)
    pasta_fato_tmp = os.path.join(PASTA_GOLD, "_fato_chunks")
    os.makedirs(pasta_fato_tmp, exist_ok=True)

    print("\n🥇 [FASE 3] Construindo tabela fato MEI...")

    # ------------------------------------------------------------------
    # Passo 1/4: Extrair DataFrame de CNPJs MEI (~67 MB na RAM)
    # ------------------------------------------------------------------
    print("   ⏳ Passo 1/4: Isolando CNPJs que são MEI...")
    df_cnpjs_mei = (
        pl.scan_parquet(os.path.join(PASTA_SILVER, "simples", "*.parquet"))
        .filter(pl.col("opcao_pelo_mei") == "S")
        .select("cnpj_basico")
        .collect()
        .unique()
    )
    gc.collect()
    ram_mei = df_cnpjs_mei.estimated_size("mb")
    print(f"      ✅ {len(df_cnpjs_mei):,} CNPJs MEI ({ram_mei:.1f} MB na RAM)")

    # ------------------------------------------------------------------
    # Passo 2/4: Carregar Empresas MEI, chunk por chunk (~134 MB total)
    # ------------------------------------------------------------------
    print("   ⏳ Passo 2/4: Carregando dados de Empresas (apenas MEI)...")
    arqs_empresas = sorted(glob.glob(os.path.join(PASTA_SILVER, "empresas", "*.parquet")))
    partes_emp: list[pl.DataFrame] = []
    for arq in arqs_empresas:
        df = pl.read_parquet(
            arq,
            columns=["cnpj_basico", "natureza_juridica", "qualificacao_responsavel", "porte_empresa"],
        )
        # SEMI-JOIN: mantém apenas linhas cujo cnpj_basico existe em df_cnpjs_mei
        df = df.join(df_cnpjs_mei, on="cnpj_basico", how="semi")
        if len(df) > 0:
            partes_emp.append(df)
        del df
    df_empresas_mei = pl.concat(partes_emp)
    del partes_emp
    gc.collect()
    ram_emp = df_empresas_mei.estimated_size("mb")
    print(f"      ✅ {len(df_empresas_mei):,} empresas MEI ({ram_emp:.1f} MB na RAM)")

    # ------------------------------------------------------------------
    # Passo 3/4: Processar Estabelecimentos chunk por chunk
    # ------------------------------------------------------------------
    print("   ⏳ Passo 3/4: Filtrando Estabelecimentos e gerando fato...")
    arqs_estab = sorted(glob.glob(os.path.join(PASTA_SILVER, "estabelecimentos", "*.parquet")))
    total_linhas   = 0
    chunks_escritos = 0

    for i, arq in enumerate(arqs_estab):
        # Lê UM chunk de Estabelecimentos (~200 MB)
        df = pl.read_parquet(arq)

        # Semi-join: descarta quem NÃO é MEI (elimina ~70% das linhas)
        df = df.join(df_cnpjs_mei, on="cnpj_basico", how="semi")
        if len(df) == 0:
            del df
            continue

        # Inner join com Empresas: adiciona natureza_juridica, porte, etc.
        df = df.join(df_empresas_mei, on="cnpj_basico", how="inner")

        # Escreve o resultado direto no disco e LIBERA a RAM
        caminho_chunk = os.path.join(pasta_fato_tmp, f"fato_{chunks_escritos:04d}.parquet")
        df.write_parquet(caminho_chunk, compression="snappy", statistics=True)
        total_linhas   += len(df)
        chunks_escritos += 1
        del df
        gc.collect()

        if (i + 1) % 10 == 0 or (i + 1) == len(arqs_estab):
            print(f"      [{i+1}/{len(arqs_estab)}] {total_linhas:,} linhas MEI acumuladas")

    # Libera as tabelas auxiliares que não precisamos mais
    del df_cnpjs_mei, df_empresas_mei
    gc.collect()

    # ------------------------------------------------------------------
    # Passo 4/4: Consolidar chunks em arquivo final (streaming)
    # ------------------------------------------------------------------
    print(f"   ⏳ Passo 4/4: Consolidando {chunks_escritos} chunks no arquivo final...")
    (
        pl.scan_parquet(os.path.join(pasta_fato_tmp, "*.parquet"))
        .sink_parquet(caminho_fato, compression="snappy")
    )

    # Limpa pasta temporária
    for f in glob.glob(os.path.join(pasta_fato_tmp, "*.parquet")):
        os.remove(f)
    os.rmdir(pasta_fato_tmp)

    # ------------------------------------------------------------------
    # Resumo final
    # ------------------------------------------------------------------
    tamanho_mb = os.path.getsize(caminho_fato) / (1024 ** 2)
    # Lemos apenas metadados para o resumo (sem carregar dados na RAM)
    schema_preview = pl.read_parquet_schema(caminho_fato)
    n_linhas = total_linhas  # já contamos durante o processamento

    print(f"\n✅ Tabela fato gerada com sucesso!")
    print(f"   📄 {os.path.abspath(caminho_fato)}")
    print(f"   📊 {n_linhas:,} linhas  |  {tamanho_mb:.1f} MB")
    print(f"\n   Schema ({len(schema_preview)} colunas):")
    for col_name, dtype in schema_preview.items():
        print(f"      {col_name:<40} {dtype}")
    print(f"\n📁 Todos os arquivos em: {os.path.abspath(PASTA_GOLD)}")


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_dimensoes()   # FASE 1: dim_*.parquet
    build_silver()      # FASE 2: silver/*/arquivo.parquet
    build_gold()        # FASE 3: mei_estabelecimentos_DATE.parquet
