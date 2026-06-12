# Documentação de Integração de Dados

Este documento descreve as estruturas de dados resultantes do **Pipeline CNPJ RF** e orienta sobre como consumir esses dados, conectando os arquivos Parquet (camada analítica) e o MongoDB (camada transacional/busca de 360 graus) ao Power BI.

---

## 1. Metadados do Arquivo Parquet (Camada Gold / OLAP)

Os arquivos Parquet gerados pelo pipeline são altamente otimizados para consultas analíticas (OLAP). Eles contêm colunas fortemente tipadas e são gerados particionados (opcional) ou em grandes blocos.

### Estrutura de Colunas e Tipos (Schema)

Os metadados principais dos DataFrames exportados em Parquet contêm as seguintes colunas e tipos de dados de acordo com o Polars:

| Nome da Coluna               | Tipo no Parquet | Descrição                                                                                     |
|------------------------------|-----------------|-----------------------------------------------------------------------------------------------|
| `cnpj_basico`                | `Utf8` (String) | Os primeiros 8 dígitos do CNPJ (identificador da raiz da empresa).                            |
| `cnpj_ordem`                 | `Utf8` (String) | Os 4 dígitos seguintes do CNPJ (identificam se é matriz ou filial).                           |
| `cnpj_dv`                    | `Utf8` (String) | Os 2 dígitos verificadores finais do CNPJ.                                                    |
| `cnpj`                       | `Utf8` (String) | CNPJ formatado ou não, dependendo do estágio (ex: `12345678000199`).                          |
| `razao_social`               | `Utf8` (String) | Nome empresarial da entidade.                                                                 |
| `natureza_juridica`          | `Int64`         | Código da natureza jurídica.                                                                  |
| `qualificacao_responsavel`   | `Int64`         | Qualificação da pessoa física responsável pela empresa.                                       |
| `capital_social`             | `Float64`       | Capital social da empresa (Double). Convertido e validado para cálculos (ex: 15000.00).       |
| `porte_empresa`              | `Int64`         | Código numérico indicando o porte da empresa (1: Não informado, 3: Micro empresa, 5: EPP).    |
| `ente_federativo_responsavel`| `Utf8` (String) | Órgão responsável no caso de entes públicos.                                                  |
| `identificador_matriz_filial`| `Int64`         | 1 para Matriz, 2 para Filial.                                                                 |
| `nome_fantasia`              | `Utf8` (String) | Nome fantasia do estabelecimento.                                                             |
| `situacao_cadastral`         | `Int64`         | Situação cadastral (01: Nula, 02: Ativa, 03: Suspensa, 04: Inapta, 08: Baixada).              |
| `data_situacao_cadastral`    | `Date` ou `Utf8`| Data do último evento da situação cadastral (YYYY-MM-DD).                                     |
| `motivo_situacao_cadastral`  | `Int64`         | Código do motivo da situação cadastral atual.                                                 |
| `cnae_fiscal_principal`      | `Int64`         | Código da atividade econômica principal (CNAE).                                               |
| `cnae_fiscal_secundaria`     | `Utf8` (String) | Códigos das atividades secundárias, separados por vírgula.                                    |
| `uf`                         | `Utf8` (String) | Sigla do estado do endereço (ex: `SP`, `RJ`).                                                 |
| `municipio`                  | `Int64`         | Código do município conforme tabela do IBGE/RFB.                                              |
| *(Demais campos de endereço)*| `Utf8` (String) | Logradouro, Número, Complemento, Bairro, CEP.                                                 |
| `data_inicio_atividade`      | `Date` ou `Utf8`| Data em que o CNPJ iniciou as atividades (YYYY-MM-DD).                                        |
| `opcao_pelo_simples`         | `Boolean`       | Se é optante pelo Simples Nacional (`True`/`False`).                                          |
| `opcao_pelo_mei`             | `Boolean`       | Se é optante pelo MEI (`True`/`False`).                                                       |

> **Nota:** Para usar o Parquet para cálculos financeiros, a coluna `capital_social` está padronizada como `Float64` em vez de texto, otimizada para o Power BI.

---

## 2. Modelagem e Estrutura no MongoDB (Camada OLTP)

O MongoDB é utilizado para **buscas pontuais super-rápidas** (ex: procurar uma empresa pelo CNPJ Básico) e oferece a visão consolidada (Matriz + Filiais) em um único documento, ideal para sistemas de consulta de clientes (Visão 360°).

### Estrutura do Documento (JSON / BSON)

A coleção se chama `empresas_mei` e o `_id` do documento corresponde ao `cnpj_basico`. Dentro deste documento, listamos os `estabelecimentos` (matrizes e filiais).

```json
{
  "_id": "12345678",
  "razao_social": "EMPRESA EXEMPLO LTDA",
  "natureza_juridica": 2062,
  "capital_social": 15000.0,
  "porte_empresa": 3,
  "qualificacao_responsavel": 49,
  "estabelecimentos": [
    {
      "cnpj": "12345678000199",
      "identificador_matriz_filial": 1,
      "nome_fantasia": "FANTASIA MATRIZ",
      "situacao_cadastral": 2,
      "data_inicio_atividade": "2010-05-12",
      "cnae_fiscal_principal": 4781400,
      "cnae_fiscal_secundarias": ["4782201", "4789099"],
      "endereco": {
        "logradouro": "AV PAULISTA",
        "numero": "1000",
        "complemento": "SALA 1",
        "bairro": "BELA VISTA",
        "cep": "01310100",
        "uf": "SP",
        "municipio_codigo": 7107
      },
      "contato": {
        "telefone_1": "11999999999",
        "telefone_2": "",
        "email": "contato@empresa.com.br"
      }
    }
  ]
}
```

### Índices Criados para Performance

No MongoDB, você pode usar os seguintes filtros que são **otimizados pelos índices** já criados pelo pipeline (buscas em milissegundos):
- **`_id`** (CNPJ Básico): Busca exata muito rápida para `O(1)`.
- **`estabelecimentos.cnae_fiscal_principal`**: Permite buscar rapidamente por nicho de mercado.
- **`estabelecimentos.cnae_fiscal_secundarias`**: Busca em arrays (Multikey Index).
- **`estabelecimentos.endereco.uf`**: Busca instantânea para filtragem geográfica (Ex: buscar todas as empresas MEI ativas no estado "SP").

---

## 3. Como Consumir os Dados com Python (Jupyter Notebook / Scripts)

Como a nossa arquitetura foi desenhada para processamento local de Big Data, o uso do ecossistema Python nativo é a forma mais rápida e robusta de realizar análises e criar gráficos, evitando problemas de memória RAM comuns em outras ferramentas.

Temos dois casos de uso principais, resolvidos por duas bibliotecas excelentes: **Polars** e **PyMongo**.

### Cenário A: Análise de Dados Agregados (Somas, Agrupamentos, Gráficos)
Para responder a perguntas que envolvem o agrupamento de **milhões de linhas** (ex: "Qual é o capital social médio por estado?" ou "Quantos MEIs abriram por ano?"), usamos a biblioteca `polars` lendo diretamente da nossa pasta Gold (`data/parquets`). 

O motor Rust do Polars (junto à compressão do Parquet) consegue varrer todo o disco em milissegundos.

**Exemplo Prático (Polars): Agrupar MEIs por Estado (UF)**
```python
import polars as pl

# Usamos scan_parquet (Lazy Execution) para "escanear" todos os parquets sem lotar a RAM
df_lazy = pl.scan_parquet("data/parquets/mei_estabelecimentos_*.parquet")

# Processa a query: Agrupa por UF e conta o número de estabelecimentos
resultado = (
    df_lazy
    .group_by("uf")
    .agg(pl.len().alias("total_empresas"))
    .sort("total_empresas", descending=True)
    .collect() # O .collect() é o que de fato dispara a execução no processador
)

print(resultado)
```

### Cenário B: Buscador e "Visão 360" (Consulta Rápida de CNPJ)
Para responder a perguntas do tipo "Agulha no Palheiro" (ex: "Quais são as filiais e os contatos do CNPJ X?" ou "Quais empresas do CNAE Y existem em uma cidade específica?"), o **MongoDB** é a ferramenta ideal.

Graças aos índices pré-calculados que criamos, o MongoDB devolve os dados em milissegundos, estruturados como dicionários Python clássicos (JSON), prontos para você manipular.

**Exemplo Prático (PyMongo + Pandas): Ficha Completa e Gráfico de um CNPJ**
```python
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient

# Conecta ao MongoDB local (onde os documentos BSON com as matrizes/filiais estão armazenados)
client = MongoClient("mongodb://localhost:27017")
db = client["cnpj_rf"]

cnpj_busca = "41367111"

# Busca rápida O(1) usando a chave primária. 
# Importante: Como o _id foi salvo como numérico no banco, convertemos a string para int()
empresa = db.empresas_mei.find_one({"_id": int(cnpj_busca)})

if empresa:
    print(f"Razão Social/Nome: {empresa.get('razao_social')}")
    print(f"Capital Social Declarado: R$ {empresa.get('capital_social')}")
    
    # Extraímos a lista de filiais (que pode ter 1 ou centenas) diretamente do documento
    estabelecimentos = empresa.get("estabelecimentos", [])
    
    # Jogamos o array BSON dentro de um DataFrame do Pandas para facilitar análises e gráficos
    df_filiais = pd.DataFrame(estabelecimentos)
    
    # Extrai a UF que está guardada dentro do sub-dicionário "endereco"
    df_filiais['uf'] = df_filiais['endereco'].apply(lambda x: x.get('uf'))
    
    # Plota rapidamente um gráfico de barras com a quantidade de filiais por estado
    contagem_uf = df_filiais['uf'].value_counts()
    
    plt.figure(figsize=(7, 4))
    contagem_uf.plot(kind='bar', color='#1E88E5', edgecolor='black')
    plt.title(f"Distribuição de Filiais - CNPJ Raiz {cnpj_busca}")
    plt.ylabel("Quantidade de Estabelecimentos")
    plt.xlabel("Estado (UF)")
    plt.xticks(rotation=0)
    plt.grid(axis='y', linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.show()
else:
    print(f"CNPJ {cnpj_busca} não encontrado.")
```

### 💡 Resumo da Arquitetura para Python:
- Use **`polars.scan_parquet`** para Data Science, Machine Learning, análises estatísticas e agregações gigantes que envolvem ler toda a base aberta.
- Use **`pymongo.find()`** para pesquisar empresas específicas, verificar situações de filiais, e popular aplicações/dashboards que exigem respostas instantâneas (onde a pessoa "digita e a tela carrega").
