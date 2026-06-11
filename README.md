# Pipeline CNPJ RF — Documentação Técnica

## Visão Geral

Pipeline de ingestão e transformação dos **Dados Abertos de CNPJ da Receita Federal**, com foco em extrair um dataset analítico de **Microempreendedores Individuais (MEI)**, pronto para consumo em ferramentas de BI ou bancos de dados analíticos.

**Fonte dos dados:** [dados-abertos-rf-cnpj.casadosdados.com.br](https://dados-abertos-rf-cnpj.casadosdados.com.br)  
**Formato de origem:** CSV sem header, separador `;`, encoding `latin1`  
**Stack:** Python 3.13 + Polars + Miniconda

---

## Por que Polars e não Spark?

O Apache Spark é a ferramenta padrão de Big Data na indústria, mas foi projetado para **clusters distribuídos** (10-1000 máquinas processando Petabytes). Para este projeto — ~40 GB de dados processados em **uma única máquina** — o Polars é a escolha mais adequada:

| Critério | Spark | Polars |
|---|---|---|
| **Setup** | Java JDK + Hadoop + PySpark (~1 GB) | `pip install polars` (20 MB) |
| **Startup** | 5-15s para iniciar a JVM | Instantâneo |
| **Velocidade (single-node)** | Overhead de serialização Java ↔ Python | **2-5x mais rápido** (motor Rust nativo, zero cópia) |
| **Uso ideal** | Cluster distribuído, Petabytes | **1 máquina**, Gigabytes-Terabytes |
| **Dependências** | JVM, Hadoop, variáveis de ambiente | Zero dependências externas |

**Nota:** O desafio principal deste pipeline não foi o volume de dados em si, mas o encoding `latin1` dos CSVs da Receita Federal. Nem o Polars nem o Spark leem `latin1` de forma nativa e eficiente — ambos carregariam o arquivo inteiro na RAM via codec Python/Java. A estratégia de leitura em chunks com conversão em memória (`io.BytesIO`) seria necessária em qualquer uma das duas ferramentas.

---

## Estrutura de Pastas

```
Pipeline CNPJ RF/
│
├── data/
│   ├── bruto/              # ZIPs baixados da Receita Federal
│   ├── extraido/           # CSVs extraídos dos ZIPs (Bronze)
│   │   ├── Empresas/
│   │   ├── Estabelecimentos/
│   │   ├── Simples/
│   │   ├── Naturezas/
│   │   ├── Qualificacoes/
│   │   ├── Motivos/
│   │   ├── Municipios/
│   │   ├── Paises/
│   │   └── Cnaes/
│   ├── silver/             # Parquets intermediários (Silver)
│   │   ├── empresas/
│   │   ├── estabelecimentos/
│   │   └── simples/
│   └── parquets/           # Outputs finais (Gold)
│       ├── mei_estabelecimentos_YYYYMMDD.parquet  ← tabela FATO
│       ├── dim_naturezas_juridicas.parquet
│       ├── dim_qualificacoes_socios.parquet
│       ├── dim_motivos_situacao.parquet
│       ├── dim_municipios.parquet
│       ├── dim_paises.parquet
│       └── dim_cnaes.parquet
│
├── coleta.py               # Download paralelo dos ZIPs da Receita
├── extrair_dados.py        # Extração dos ZIPs + remoção dos ZIPs
├── build_mei_dataset.py    # Pipeline principal (Bronze → Silver → Gold)
├── cnpj-metadados.pdf      # Dicionário de dados oficial da Receita Federal
├── .gitignore
└── DOCUMENTACAO.md
```

---

## Scripts

### `coleta_extracao.py` — Download dos Arquivos

Baixa todos os arquivos `.zip` da página da Receita Federal usando `requests` com `ThreadPoolExecutor` (downloads paralelos, até 4 simultâneos).

- **Entrada:** URL do servidor da Receita Federal  
- **Saída:** `data/bruto/*.zip`
- **Idempotente:** pula arquivos já baixados

Extrai todos os `.zip` de `data/bruto/` para subpastas em `data/extraido/`, agrupando por categoria (ex: `Empresas0.zip`, `Empresas1.zip` → pasta `data/extraido/Empresas/`). Após extração bem-sucedida, **deleta o `.zip`** para liberar espaço em disco.

- **Entrada:** `data/bruto/*.zip`  
- **Saída:** `data/extraido/<Categoria>/`
- **Lógica de pasta:** regex `\d+$` remove o sufixo numérico do nome do arquivo

```bash
python coleta_extracao.py
```

---

### `build_mei_dataset.py` — Pipeline Principal

Arquivo central do projeto. Implementa a **Arquitetura Medalhão** em 3 fases.

```bash
python build_mei_dataset.py
```

---

## Arquitetura Medalhão

```
BRONZE          SILVER                    GOLD
data/extraido/  data/silver/              data/parquets/
─────────────   ──────────────────        ────────────────────────────────
CSV latin1      Parquet por arquivo       Parquets finais prontos
sem header      tipos otimizados          para consumo analítico
                (um por vez → sem OOM)    (tabela fato + dimensões)
```

### Por que 3 camadas?

Os CSVs da Receita Federal têm dois problemas sérios para Big Data:

1. **Encoding latin1:** O motor Rust do Polars só aceita UTF-8 nativamente. Forçar latin1 faz o Python carregar o arquivo **inteiro na RAM** antes de passar para o Polars (1 arquivo de 1.5GB → 3GB+ de RAM). Com 10 arquivos de Estabelecimentos, isso é um `MemoryError` garantido.

2. **Sem header, separador diferente:** Requer configuração manual de schema.

A solução é **separar o problema de encoding do problema de processamento**:
- A camada Silver resolve o encoding convertendo linha a linha (custo de RAM ≈ 0)
- A camada Gold usa `scan_parquet` (nativo Rust, lazy, streaming real) para o JOIN

---

## Fase 1 — Dimensões (Bronze → Gold)

As tabelas de domínio são **pequenas** (máximo ~5MB cada). Para elas, o `read_csv` com fallback de encoding do Python é viável sem risco de OOM.

| Pasta (Bronze)  | Parquet (Gold)                    | Linhas |
|-----------------|-----------------------------------|--------|
| `Naturezas/`    | `dim_naturezas_juridicas.parquet` | ~91    |
| `Qualificacoes/`| `dim_qualificacoes_socios.parquet`| ~68    |
| `Motivos/`      | `dim_motivos_situacao.parquet`    | ~63    |
| `Municipios/`   | `dim_municipios.parquet`          | ~5.572 |
| `Paises/`       | `dim_paises.parquet`              | ~255   |
| `Cnaes/`        | `dim_cnaes.parquet`               | ~1.359 |

Todas têm apenas duas colunas: `codigo` (UInt32) e `descricao` (String).

---

## Fase 2 — Silver (Bronze → Silver)

Converte cada CSV grande para Parquet dividindo-o em **chunks de 1 milhão de linhas**, processando um chunk por vez para evitar Out Of Memory (OOM):

```
CSV latin1 (disco)
    ↓
Python abre e lê 1 milhão de linhas (≈ 200 MB de RAM)
    ↓
Linhas são agrupadas em string e encodadas para UTF-8 em memória (io.BytesIO)
    ↓
Polars read_csv lê o buffer nativamente (motor Rust)
    ↓
_cast_schema() → aplica tipos corretos
    ↓
write_parquet() → silver/<categoria>/<arquivo>_0000.parquet
    ↓
del df e buffer → gc.collect() libera a memória RAM IMEDIATAMENTE
    ↓
lê os próximos 1M de linhas...
```

O pico de RAM em qualquer momento é de apenas **~400 MB** por chunk. O CSV gigante gera múltiplos arquivos menores (chunks) no final. **Idempotente:** arquivos que já possuem o chunk `_0000.parquet` são pulados.
---

## Fase 3 — Gold (Silver → Fato)

Etapa final: cruzar Simples + Empresas + Estabelecimentos para gerar a **Tabela Fato MEI**.

### O Problema do "Spill to Disk"

Usar `LazyFrame` com `is_in()` e `sink_parquet()` parecia ideal, mas o Polars tenta materializar o plano inteiro na RAM antes de escrever. Com 70M+ linhas e um HashSet de 16.7M CNPJs, isso causava:
- **OOM** (Out of Memory) em PCs com 16 GB de RAM, ou
- **Spill to Disk** (SSD a 100% de uso), travando a máquina por completo.

### Solução: Processamento EAGER chunk por chunk com SEMI-JOIN

Em vez de deixar o Polars planejar tudo de uma vez, nós controlamos cada passo manualmente:

```
Passo 1/4 — Isolar CNPJs MEI (~67 MB na RAM)
    Lê tabela Simples → filtra opcao_pelo_mei == 'S' → DataFrame de 1 coluna

Passo 2/4 — Carregar Empresas MEI (~134 MB na RAM)
    Lê cada chunk de Empresas → SEMI-JOIN com CNPJs MEI → concat resultado

Passo 3/4 — Processar Estabelecimentos (chunk por chunk, ~200 MB por vez)
    Para CADA parquet de Estabelecimentos:
        ↓ pl.read_parquet(chunk)           ← lê ~1M linhas (~200 MB)
        ↓ semi-join com df_cnpjs_mei       ← descarta ~70% das linhas (não-MEI)
        ↓ inner join com df_empresas_mei   ← adiciona porte, natureza jurídica
        ↓ write_parquet(fato_chunk)        ← escreve no disco imediatamente
        ↓ del df → gc.collect()            ← RAM liberada antes do próximo chunk

Passo 4/4 — Consolidar chunks no arquivo final (streaming)
    scan_parquet("_fato_chunks/*.parquet").sink_parquet(final.parquet)
    Limpa a pasta temporária de chunks.
```

**Pico de RAM:** ~600 MB (vs 10+ GB do LazyFrame).

**Por que SEMI-JOIN e não `is_in()`?**
- `is_in(Series)` cria um HashSet Python de 16.7M entradas na RAM (~470 MB)
- `semi-join` usa o motor Rust nativo do Polars (hash join otimizado, ~67 MB)
- Sem `DeprecationWarning` do Polars sobre `is_in` com coleções do mesmo tipo

**Resultado final:** Um único arquivo `.parquet` compactado (`mei_estabelecimentos_YYYYMMDD.parquet`) contendo a Tabela Fato modelada.

---

## Schema da Tabela Fato (33 colunas)

O Parquet `mei_estabelecimentos_YYYYMMDD.parquet` contém 30 colunas de **Estabelecimentos** + 3 colunas de **Empresas**, cruzadas via `cnpj_basico`:

| # | Coluna | Tipo | Origem |
|---|---|---|---|
| 1 | `cnpj_basico` | `UInt32` | Estabelecimentos (chave de JOIN) |
| 2 | `cnpj_ordem` | `UInt16` | Estabelecimentos |
| 3 | `cnpj_dv` | `UInt8` | Estabelecimentos |
| 4 | `identificador_matriz_filial` | `UInt8` | Estabelecimentos |
| 5 | `nome_fantasia` | `String` | Estabelecimentos |
| 6 | `situacao_cadastral` | `UInt8` | Estabelecimentos |
| 7 | `data_situacao_cadastral` | `UInt32` | Estabelecimentos |
| 8 | `motivo_situacao_cadastral` | `UInt8` | Estabelecimentos |
| 9 | `nome_cidade_exterior` | `String` | Estabelecimentos |
| 10 | `pais` | `UInt16` | Estabelecimentos |
| 11 | `data_inicio_atividade` | `UInt32` | Estabelecimentos |
| 12 | `cnae_fiscal_principal` | `UInt32` | Estabelecimentos |
| 13 | `cnae_fiscal_secundaria` | `String` | Estabelecimentos |
| 14 | `tipo_logradouro` | `String` | Estabelecimentos |
| 15 | `logradouro` | `String` | Estabelecimentos |
| 16 | `numero` | `String` | Estabelecimentos |
| 17 | `complemento` | `String` | Estabelecimentos |
| 18 | `bairro` | `String` | Estabelecimentos |
| 19 | `cep` | `UInt32` | Estabelecimentos |
| 20 | `uf` | `String` | Estabelecimentos |
| 21 | `municipio` | `UInt32` | Estabelecimentos |
| 22 | `ddd_1` | `UInt16` | Estabelecimentos |
| 23 | `telefone_1` | `String` | Estabelecimentos |
| 24 | `ddd_2` | `UInt16` | Estabelecimentos |
| 25 | `telefone_2` | `String` | Estabelecimentos |
| 26 | `ddd_fax` | `UInt16` | Estabelecimentos |
| 27 | `fax` | `String` | Estabelecimentos |
| 28 | `correio_eletronico` | `String` | Estabelecimentos |
| 29 | `situacao_especial` | `String` | Estabelecimentos |
| 30 | `data_situacao_especial` | `UInt32` | Estabelecimentos |
| 31 | `natureza_juridica` | `UInt16` | Empresas |
| 32 | `qualificacao_responsavel` | `UInt8` | Empresas |
| 33 | `porte_empresa` | `UInt8` | Empresas |

### Decisões de Tipagem

| Tipo | Colunas | Motivo |
|---|---|---|
| `UInt32` | `cnpj_basico`, `cep`, `cnae_fiscal_principal`, `municipio`, datas | Códigos numéricos de até 8 dígitos — 4 bytes vs 10 de String |
| `UInt16` | `cnpj_ordem`, `pais`, `ddd_*`, `natureza_juridica` | Valores até 65.535 — 2 bytes |
| `UInt8` | `cnpj_dv`, `situacao_cadastral`, `porte_empresa`, etc. | Valores até 255 — 1 byte |
| `String` | `nome_fantasia`, `logradouro`, `numero`, etc. | Texto livre ou valores mistos (ex: `numero` pode ser `"S/N"`) |

### Tabela Sócios — Por que não incluída?

Por definição legal, o MEI é um empresário individual — ele próprio é o único sócio. A tabela de Sócios só adicionaria redundância sem valor analítico. Foi excluída intencionalmente para reduzir volume e tempo de processamento.

---

## Modelagem Dimensional (Star Schema)

```
dim_naturezas_juridicas   ───┐
dim_qualificacoes_socios   ───┤
dim_motivos_situacao       ───┤    
dim_municipios             ───┼──── mei_estabelecimentos_YYYYMMDD  (FATO)
dim_paises                 ───┤
dim_cnaes                  ───┘
```

A tabela fato mantém apenas os **códigos numéricos** (chaves estrangeiras). Ferramentas como DuckDB, Power BI ou Spark fazem o lookup nas tabelas de dimensão em tempo de query. Isso evita repetir strings longas como `"EMPRESÁRIO INDIVIDUAL"` milhões de vezes.

**Exemplo de query com DuckDB:**
```sql
SELECT 
    f.razao_social,
    m.descricao AS municipio,
    c.descricao AS atividade_principal,
    COUNT(*) AS estabelecimentos
FROM 'data/parquets/mei_estabelecimentos_*.parquet' f
LEFT JOIN 'data/parquets/dim_municipios.parquet' m ON f.municipio = m.codigo
LEFT JOIN 'data/parquets/dim_cnaes.parquet'      c ON f.cnae_fiscal_principal = c.codigo
GROUP BY 1, 2, 3
ORDER BY 4 DESC
LIMIT 20;
```

---

## Convenção de Nomenclatura dos Parquets

| Prefixo | Tipo | Exemplo |
|---|---|---|
| `mei_` | Tabela fato (filtrada) | `mei_estabelecimentos_20251214.parquet` |
| `dim_` | Tabela de dimensão/domínio | `dim_municipios.parquet` |

O sufixo `_YYYYMMDD` na tabela fato é o **snapshot date** — a data em que o pipeline foi executado. Permite manter histórico de múltiplos snapshots e fazer queries com glob (`*.parquet`).

---

## .gitignore

Arquivos de dados não são versionados (são grandes demais e reproduzíveis):

```
*.parquet
*.zip
*.csv
data/extraido/*
data/silver/*
```

---

## Como Rodar o Pipeline Completo

```bash
# 1. Baixar os ZIPs da Receita Federal
python coleta.py

# 2. Extrair os ZIPs e remover os originais
python extrair_dados.py

# 3. Rodar o pipeline de transformação (Bronze → Silver → Gold)
python build_mei_dataset.py
```

> **O pipeline é idempotente.** Se interrompido, pode ser reiniciado — arquivos já processados são pulados automaticamente via checagem de existência do Parquet de saída.

---

## 🍃 Integração com MongoDB (Camada Operacional)

Além do armazenamento em Parquet para consultas analíticas pesadas (OLAP), o projeto conta com uma **Integração com MongoDB (OLTP)** para permitir consultas cadastrais pontuais rápidas (360° Lookup) por CNPJ básico, CNAE e UF.

### Arquitetura Híbrida (HTAP)
* **DuckDB + Parquet**: Utilizado para realizar grandes agregações, cálculos de média de capital social e relatórios analíticos de BI.
* **MongoDB (BSON)**: Utilizado para buscas detalhadas rápidas de empresas e suas filiais de forma denormalizada.

### 📝 Estrutura do Documento e Resolução de Duplicidades
Para aproveitar a modelagem orientada a documentos, o script de integração agrupa os estabelecimentos pelo `cnpj_basico`. 
* Em vez de salvar cada filial em um registro separado (como no SQL/Parquet), salvamos um único documento por empresa (com o `_id` sendo o `cnpj_basico`) contendo um array de `estabelecimentos` (aninhando a matriz e todas as suas filiais no mesmo local).
* Isso é implementado via operações em lote (**Bulk Write**) no MongoDB usando `UpdateOne(..., upsert=True)` com `$setOnInsert` para os metadados da empresa e `$push` com `$each` para carregar e ir acumulando os estabelecimentos no array de forma rápida e sem chaves duplicadas.

### 🗄️ Onde o banco de dados é criado e armazenado?
Como o banco de dados roda localmente:
1. **Nome do Banco**: `cnpj_rf`
2. **Nome da Coleção**: `empresas_mei`
3. **Localização Física dos Arquivos**:
   * **Via Docker (Recomendado)**: Os dados ficam armazenados em um volume gerenciado pelo Docker (`mongo_data`). No Windows (WSL2), esses dados são salvos no disco virtual do Docker, localizado tipicamente em `%USERPROFILE%\AppData\Local\Docker\wsl\data\ext4.vhdx`.
   * **Instalação Nativa (MSI)**: Se instalado diretamente no Windows, os arquivos do banco ficam na pasta de dados padrão configurada na instalação (geralmente em `C:\Program Files\MongoDB\Server\<versão>\data\`).

---

### 🚀 Como Configurar e Rodar o MongoDB Local

#### 1. Iniciar o Banco via Docker Desktop
Com o **Docker Desktop** aberto e ativo, rode o seguinte comando no PowerShell para subir a imagem oficial do MongoDB:
```powershell
docker run -d --name mongo-local -p 27017:27017 -v mongo_data:/data/db mongo:latest
```

#### 2. Rodar a Carga de Integração
Para ler os arquivos Parquet Gold, estruturar os documentos BSON com estabelecimentos aninhados e importar no MongoDB com os índices corretos, execute:
```bash
conda run -n base python integrate_mongodb.py
```

O script criará automaticamente os seguintes índices após a importação para garantir buscas em milissegundos:
* `_id`: Chave primária baseada no `cnpj_basico`.
* `estabelecimentos.cnae_fiscal_principal`: Índice para buscas rápidas por atividade econômica principal.
* `estabelecimentos.cnae_fiscal_secundarias`: Índice *multikey* para filtrar por atividades secundárias contidas no array.
* `estabelecimentos.endereco.uf`: Índice para filtragem rápida por estado de origem.

---

### 🔍 Exemplo de Consultas no MongoDB (Python / MongoDB Compass)

**Pesquisa de Ficha Cadastral Completa por CNPJ (Busca direta por ID):**
```python
empresa = db.empresas_mei.find_one({"_id": 41367111})
```

**Busca de empresas no estado do Maranhão (MA) que atuam em um CNAE específico:**
```python
empresas = db.empresas_mei.find({
    "estabelecimentos.endereco.uf": "MA",
    "estabelecimentos.cnae_fiscal_principal": 4773300
})
```

