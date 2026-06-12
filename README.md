# Pipeline CNPJ RF — Ingestão, Transformação e Visualização de Dados de MEIs

## Visão Geral

Este projeto consiste em um pipeline de engenharia de dados completo para processamento, armazenamento e visualização dos **Dados Abertos de CNPJ da Receita Federal**. O foco principal é a extração, tratamento e consolidação de um dataset analítico de **Microempreendedores Individuais (MEI)** do Brasil.

O pipeline adota a **Arquitetura Medalhão** (Bronze → Silver → Gold) utilizando **Python 3.13** e **Polars** para transformação de alto desempenho. O armazenamento analítico (OLAP) é feito em arquivos compactados **Parquet**, enquanto a camada operacional e de busca rápida (OLTP/Lookup) utiliza o **MongoDB**. Por fim, uma aplicação **Streamlit** fornece análises visuais ricas e um mecanismo de consulta cadastral 360°.

* **Fonte dos dados:** [dados-abertos-rf-cnpj.casadosdados.com.br](https://dados-abertos-rf-cnpj.casadosdados.com.br)
* **Formato original:** CSV sem cabeçalho, delimitador `;`, codificação `latin1`.
* **Stack Principal:** Python 3.13 + Polars + PyArrow + MongoDB + Streamlit + Plotly.

---

## Por que Polars e não Spark?

Embora o Apache Spark seja o padrão da indústria para Big Data em clusters distribuídos, este projeto processa cerca de **40 GB** de dados brutos em um ambiente de **máquina única (single-node)**. Para esse cenário, o **Polars** (escrito em Rust) provou-se consideravelmente superior:

| Critério | Apache Spark | Polars (Rust) |
|---|---|---|
| **Setup & Instalação** | JVM (Java JDK) + Hadoop + PySpark (~1 GB) | `pip install polars` (20 MB) |
| **Tempo de Inicialização** | 5 a 15 segundos para carregar a JVM | Instantâneo |
| **Velocidade (Single-Node)** | Overhead de serialização e IPC entre Java/Python | **2x a 5x mais rápido** (motor Rust nativo, multithread eficiente e zero copy) |
| **Uso de Memória** | Alto consumo e garbage collection da JVM | Baixo consumo com alocação otimizada em Rust |
| **Dependências** | Complexo (JVM, caminhos de classe, SparkConf) | Nenhuma dependência externa complexa |

**Nota técnica:** O gargalo do processo reside no fato de os CSVs originais estarem salvos em codificação `latin1`. Motores de alta performance (como Rust no Polars ou C++ no Spark) exigem strings `UTF-8` nativamente. O pipeline resolve isso lendo os arquivos em chunks de 1 milhão de linhas via streaming e realizando a decodificação em memória (`io.BytesIO`) antes de entregar o DataFrame ao Polars, mantendo o pico de uso de RAM sob controle (~400 MB).

---

## Estrutura do Workspace e Arquivos

```
Pipeline CNPJ RF/
│
├── data/
│   ├── bruto/              # Arquivos .zip baixados da Receita Federal
│   ├── extraido/           # CSVs originais extraídos (Camada Bronze)
│   │   ├── Empresas/
│   │   ├── Estabelecimentos/
│   │   ├── Simples/
│   │   ├── Socios/
│   │   └── ... (Cnaes, Municipios, Paises, Naturezas, etc.)
│   ├── silver/             # Arquivos Parquet intermediários tipados (Camada Silver)
│   │   ├── empresas/
│   │   ├── estabelecimentos/
│   │   ├── socios/
│   │   └── simples/
│   └── parquets/           # Datasets consolidados e otimizados (Camada Gold)
│       ├── mei_estabelecimentos_YYYYMMDD.parquet  ← Tabela Fato MEI (Unificada com Sócios)
│       ├── dim_naturezas_juridicas.parquet
│       ├── dim_qualificacoes_socios.parquet
│       ├── dim_motivos_situacao.parquet
│       ├── dim_municipios.parquet
│       ├── dim_paises.parquet
│       └── dim_cnaes.parquet
│
├── dashboard/              # Painel Streamlit e componentes visuais
│   ├── app.py              # Ponto de entrada e roteamento de abas
│   ├── config.py           # Estilos (paleta de cores HSL), layouts e constantes
│   ├── data_loader.py      # Carregamento e cache dinâmico de dados (Polars & MongoDB)
│   ├── mongo_client.py     # Singleton do cliente de conexão com MongoDB
│   ├── requirements.txt    # Dependências exclusivas do dashboard
│   ├── components/         # Componentes reutilizáveis do dashboard
│   │   ├── charts.py       # Gerador centralizado de gráficos Plotly
│   │   ├── filters.py      # Painéis de filtros laterais/superiores
│   │   └── kpi_cards.py    # Cartões de métricas em CSS/HTML moderno
│   └── views/              # Páginas e dashboards específicos
│       ├── visao_geral.py       # KPIs gerais e situação cadastral do MEI
│       ├── analise_temporal.py  # Histórico de aberturas, fechamentos e capital social (>= 2009)
│       ├── analise_geografica.py# Mapas coropléticos de distribuição geográfica (UFs)
│       ├── analise_cnae.py      # Estatísticas de atividades econômicas (Top CNAEs)
│       └── consulta_cadastral.py# Mecanismo de busca 360° integrado ao MongoDB
│
├── coleta_extracao.py      # Script unificado para download paralelo dos ZIPs e descompactação
├── build_mei_dataset.py    # Pipeline de processamento ETL (Bronze → Silver → Gold)
├── integrate_mongodb.py    # Carga otimizada em batches no MongoDB (OLTP / Operational)
├── main.ipynb              # Notebook Jupyter para experimentações e análises
├── .gitignore              # Ignora arquivos de dados analíticos volumosos
└── README.md               # Esta documentação
```

---

## O Pipeline de Transformação (Arquitetura Medalhão)

```
BRONZE                 SILVER                   GOLD
data/extraido/         data/silver/             data/parquets/
───────────────        ─────────────────        ─────────────────────────────────
CSV latin1             Parquet por chunk        Parquet consolidado estruturado
Sem cabeçalhos         Tipos de dados nativos   (Tabela Fato MEI + Dimensões)
                       (Conversão p/ UTF-8)
```

### Camada Bronze (Dados Extraídos)
Os arquivos `.zip` do portal público são baixados pelo script `coleta_extracao.py` em múltiplos downloads concorrentes (usando `ThreadPoolExecutor`). Logo em seguida, os arquivos são descompactados nas subpastas apropriadas e os arquivos brutos compactados são apagados para economizar espaço de armazenamento.

### Camada Silver (Parquet Tipado por Chunk)
Para evitar falhas de memória (OOM) em máquinas com menor capacidade, o arquivo `build_mei_dataset.py` divide a conversão dos arquivos gigantescos (como `Estabelecimentos` e `Empresas`) em blocos (chunks) de 1.000.000 de linhas. Cada bloco é decodificado de `latin1` para `utf-8` na RAM de maneira eficiente e salvo como arquivos Parquet compactados individuais dentro do diretório `data/silver/`.

### Camada Gold (Cruzamento e Consolidação)
O principal objetivo desta fase é consolidar as tabelas num dataset único de **Microempreendedores Individuais (MEI)**.
Para contornar o gargalo da CPU e uso de memória de grandes queries de JOIN analítico, a consolidação executa as seguintes etapas:
1. **Identificação de MEIs**: Lê os metadados do Simples Nacional (`data/silver/simples/`) e isola apenas os CNPJs com a flag `opcao_pelo_mei == 'S'`.
2. **Filtragem de Empresas**: Executa um `SEMI-JOIN` entre as empresas e a lista de CNPJs MEI isolados, reduzindo drasticamente o dataset em RAM.
3. **Consolidação em Bloco**: Para cada chunk de Estabelecimentos na camada Silver, realiza o cruzamento com as Empresas MEI filtradas e também faz o cruzamento (`left-join`) com a tabela de **Sócios**.
4. **Resolução de Relações de Sócios**: Por definição do modelo de negócios do MEI (Microempreendedor Individual), a empresa é composta por **apenas um único sócio proprietário**. Portanto, a relação entre estabelecimentos e sócios é de **1-para-1**, permitindo consolidar os atributos dos sócios diretamente na linha do estabelecimento sem inflar a cardinalidade ou gerar duplicidade cartesiana.
5. **Gravação**: Gera a Fato consolidada e unificada no arquivo final compactado `mei_estabelecimentos_YYYYMMDD.parquet`.

---

## Schema da Tabela Fato Gold (39 colunas)

O dataset final `mei_estabelecimentos_YYYYMMDD.parquet` reúne 30 colunas de Estabelecimentos, 4 colunas de Empresas e 5 colunas do Sócio Proprietário:

| Índice | Coluna | Tipo Polars | Descrição |
|---|---|---|---|
| 1 | `cnpj_basico` | `UInt32` | Identificador base do CNPJ (chave de cruzamento) |
| 2 | `cnpj_ordem` | `UInt16` | Sufixo identificador do CNPJ (ex: 0001) |
| 3 | `cnpj_dv` | `UInt8` | Dígitos verificadores do CNPJ |
| 4 | `identificador_matriz_filial` | `UInt8` | Indica se é Matriz (1) ou Filial (2) |
| 5 | `nome_fantasia` | `String` | Nome de fachada/fantasia |
| 6 | `situacao_cadastral` | `UInt8` | Estado cadastral da empresa (1: Nula, 2: Ativa, 3: Suspensa, 4: Inapta, 8: Baixada) |
| 7 | `data_situacao_cadastral` | `UInt32` | Data de alteração do status (AAAAMMDD) |
| 8 | `motivo_situacao_cadastral` | `UInt8` | Motivo de baixa ou inaptidão |
| 9 | `nome_cidade_exterior` | `String` | Cidade internacional, se aplicável |
| 10 | `pais` | `UInt16` | Código do país de origem |
| 11 | `data_inicio_atividade` | `UInt32` | Data de fundação oficial da empresa (AAAAMMDD) |
| 12 | `cnae_fiscal_principal` | `UInt32` | Código da atividade econômica principal (CNAE) |
| 13 | `cnae_fiscal_secundaria` | `String` | Lista de CNAEs secundários separados por vírgula |
| 14 | `tipo_logradouro` | `String` | Classificação do endereço (Rua, Av, etc) |
| 15 | `logradouro` | `String` | Nome do logradouro |
| 16 | `numero` | `String` | Número físico do endereço |
| 17 | `complemento` | `String` | Detalhes complementares de localização |
| 18 | `bairro` | `String` | Bairro onde o negócio está instalado |
| 19 | `cep` | `UInt32` | Código de Endereçamento Postal |
| 20 | `uf` | `String` | Estado federativo da sede (UF) |
| 21 | `municipio` | `UInt32` | Código IBGE do município |
| 22 | `ddd_1` | `UInt16` | DDD do telefone de contato primário |
| 23 | `telefone_1` | `String` | Número de telefone principal |
| 24 | `ddd_2` | `UInt16` | DDD do telefone secundário |
| 25 | `telefone_2` | `String` | Número de telefone secundário |
| 26 | `ddd_fax` | `UInt16` | DDD de fax secundário |
| 27 | `fax` | `String` | Linha de fax |
| 28 | `correio_eletronico` | `String` | E-mail corporativo cadastrado |
| 29 | `situacao_especial` | `String` | Status especiais cadastrais |
| 30 | `data_situacao_especial` | `UInt32` | Data do status especial |
| 31 | `natureza_juridica` | `UInt16` | Código de natureza jurídica (geralmente 2135 para MEIs) |
| 32 | `qualificacao_responsavel`| `UInt8` | Qualificação legal da diretoria |
| 33 | `porte_empresa` | `UInt8` | Código do porte legal (geralmente 1 ou 5 para MEI) |
| 34 | `capital_social` | `Float64` | Valor nominal declarado de capital social |
| 35 | `identificador_socio` | `UInt8` | Tipo de pessoa do sócio (1: Jurídica, 2: Física) |
| 36 | `nome_socio_razao_social`| `String` | Nome civil completo do Proprietário / Sócio |
| 37 | `cnpj_cpf_socio` | `String` | CPF mascarado ou CNPJ do sócio |
| 38 | `qualificacao_socio` | `UInt8` | Código correspondente à qualificação (ex: Titular) |
| 39 | `data_entrada_sociedade` | `UInt32` | Data em que ingressou na sociedade (AAAAMMDD) |

---

## Modelagem Dimensional (Star Schema)

A tabela fato final mantém apenas chaves numéricas (`UInt32`, `UInt16`, `UInt8`) que se relacionam com as tabelas de dimensões indexadas no disco (Gold). Isso reduz drasticamente o tamanho do arquivo final e otimiza o cache de consultas:

```
dim_naturezas_juridicas   ───┐
dim_qualificacoes_socios  ───┤
dim_motivos_situacao      ───┤    
dim_municipios            ───┼──── mei_estabelecimentos_YYYYMMDD  (FATO)
dim_paises                ───┤
dim_cnaes                 ───┘
```

---

## 🍃 Camada Operacional com MongoDB

Para fins de consultas de busca rápida ou fichas cadastrais (padrão OLTP), os dados consolidados da tabela Gold são importados no **MongoDB**.

### Estrutura Orientada a Documentos (Aninhada)
Aproveitando as propriedades do formato BSON, os dados são denormalizados e agrupados por `cnpj_basico`. A estrutura aninha as filiais (`estabelecimentos`) e os `socios` em arrays no mesmo documento:

```json
{
  "_id": 41367111,
  "razao_social": "ERIC AMORIM SERVICOS DE APOIO ADMINISTRATIVO LTDA",
  "natureza_juridica": 2135,
  "capital_social": 1500.0,
  "porte_empresa": 1,
  "opcao_pelo_simples": "S",
  "opcao_pelo_mei": "S",
  "socios": [
    {
      "identificador_socio": 2,
      "nome_socio_razao_social": "ERIC AMORIM",
      "cnpj_cpf_socio": "***489128**",
      "qualificacao_socio": 65,
      "data_entrada_sociedade": 20210515
    }
  ],
  "estabelecimentos": [
    {
      "cnpj_ordem": 1,
      "cnpj_dv": 47,
      "identificador_matriz_filial": 1,
      "nome_fantasia": "AMORIM APOIO E SERVICOS",
      "situacao_cadastral": 2,
      "data_situacao_cadastral": 20210515,
      "data_inicio_atividade": 20210515,
      "cnae_fiscal_principal": 8211300,
      "cnae_fiscal_secundarias": [8219999, 7319002],
      "endereco": {
        "tipo_logradouro": "AVENIDA",
        "logradouro": "PAULISTA",
        "numero": "1000",
        "complemento": "SALA 51",
        "bairro": "BELA VISTA",
        "cep": 1311000,
        "uf": "SP",
        "municipio": 3550308
      },
      "contato": {
        "ddd_1": 11,
        "telefone_1": "998877665",
        "ddd_2": null,
        "telefone_2": null,
        "correio_eletronico": "contato@amorim.com"
      }
    }
  ]
}
```

### Otimizações e Estratégia de Carga (Bulk Write)
* **Limpeza e Idempotência**: O script `integrate_mongodb.py` realiza um `drop_database("cnpj_rf")` completo no início para limpar dados legados e assegurar integridade estrutural.
* **Bulk Writes**: Insere em lotes (`ordered=False`) de 50.000 registros para maximizar a taxa de transferência.
* **Agrupamento Local**: Agrupa as filiais em memória por `cnpj_basico` dentro de cada lote, realizando um único `UpdateOne(..., upsert=True)` usando `$setOnInsert` para dados corporativos e `$push` com `$each` para anexar estabelecimentos.
* **Índices Criados**:
  * `_id` (CNPJ Básico primário)
  * `estabelecimentos.cnae_fiscal_principal` (Índice padrão)
  * `estabelecimentos.cnae_fiscal_secundarias` (Índice *multikey* para busca em arrays de inteiros)
  * `estabelecimentos.endereco.uf` (Filtro geográfico)

---

## 📊 Dashboard Analítico (Streamlit)

A aplicação de BI integrada, contida em `dashboard/`, foi desenvolvida com foco em alta performance e experiência visual rica.

### Arquitetura do Dashboard
A aplicação está estruturada de maneira modular para facilitar manutenções:
* **`app.py`**: Gerenciador central de abas e layout da aplicação (painel lateral e cabeçalho customizados).
* **`config.py`**: Configuração central de paleta de cores (HSL harmonizado com tema escuro premium), tipografia moderna e constantes.
* **`data_loader.py`**: Concentra todas as leituras de dados analíticos (via arquivo Parquet com motor Polars e Lazy Evaluation) e consultas pontuais à API do MongoDB. Possui sistema de cache (`@st.cache_data`) para aceleração de gráficos recorrentes.
* **`components/`**: Arquivos isolados para renderização de cards de métricas (`kpi_cards.py`), criação de painéis de filtros (`filters.py`) e centralização dos gráficos customizados do Plotly com tema integrado (`charts.py`).
* **`views/`**: Telas independentes contendo a lógica de cada aba analítica.

### Seções e Funcionalidades do Dashboard

1. **Visão Geral**:
   * **KPIs Dinâmicos**: Exibição em cards modernos de: total de MEIs registrados, número de MEIs ativos, porcentagem de atividade e média global de capital social declarado.
   * **Situação Cadastral**: Gráfico de barras verticais indicando a quantidade de MEIs em cada estado cadastral (Ativo, Baixado, Inapto, Suspenso).
   * *Obs: Gráficos de barra que envolviam comparação de portes (ME e EPP) foram removidos para manter o dashboard 100% focado no nicho de MEI.*

2. **Análise Temporal**:
   * **Filtro Seguro (>= 2009)**: Os dados do dashboard são rigidamente restritos a anos superiores ou iguais a 2009. Esta decisão de engenharia corrige distorções de data anteriores e remove o pico anômalo de capital social observado no ano de 2007 (uma vez que a lei que rege a criação do MEI entrou em vigor em **2009**).
   * **Aberturas Mensais**: Gráfico de linhas temporais que exibe o volume de novos registros mês a mês ao longo dos anos selecionados.
   * **Aberturas vs Fechamentos Anual**: Gráfico de linhas duplas permitindo comparar diretamente o total de MEIs criados com o total de MEIs encerrados (baixados) ao longo do tempo.
   * **Média de Capital Social**: Evolução anual do valor médio declarado no capital social.

3. **Análise Geográfica**:
   * **Mapa de Calor (Coroplético)**: Visualização da distribuição dos MEIs pelos estados do Brasil utilizando o mapa interactivo do Plotly.
   * **Tabela Auxiliar**: Ordenação das UFs pelo número absoluto de registros e proporção.
   * *Obs: O gráfico Treemap foi removido para evitar excesso visual e sobreposição de rótulos.*

4. **Análise por Atividade Econômica (CNAE)**:
   * **Top 10 CNAEs**: Gráfico de barras horizontais indicando quais são as principais atividades econômicas escolhidas pelos Microempreendedores Individuais.
   * *Obs: Gráficos complexos como Sunburst e cruzamentos de CNAE x Situação Cadastral foram removidos para focar em clareza.*

5. **Consulta Cadastral (360° Lookup)**:
   * Busca em tempo real baseada diretamente na coleção operacional do **MongoDB**.
   * O usuário pode buscar por **CNPJ** (completo ou básico) ou **Razão Social/Nome Fantasia**.
   * Exibição de uma ficha cadastral premium no estilo card de negócios, contendo dados corporativos básicos, endereço completo e dados de contato.
   * **Seção de Sócios**: Mostra o nome do Proprietário / Sócio Titular do MEI e seu CPF mascarado.
   * **Sanitização de Strings**: Tratamento rigoroso na leitura dos dados para garantir que valores ausentes ou strings literais `"None"` e `"NONE"` sejam limpos, apresentando espaços em branco ou omitindo campos não preenchidos.
   * *Obs: A filtragem analítica secundária por UF+CNAE foi removida para tornar a experiência de consulta direta extremamente objetiva.*

---

## Como Instalar e Executar o Projeto

### Pré-requisitos
* Conda (Miniconda ou Anaconda) ou Python 3.13 instalado.
* Docker instalado (para rodar o MongoDB localmente) ou uma instância do MongoDB rodando na porta `27017`.

### Passo a Passo

#### 1. Clonar o projeto e criar o ambiente virtual
```bash
# Criar ambiente Conda
conda create -n pipeline-mei python=3.13 -y
conda activate pipeline-mei

# Instalar dependências gerais
pip install polars pyarrow pymongo streamlit plotly requests beautifulsoup4
```

#### 2. Executar download e extração dos dados (Bronze)
```bash
python coleta_extracao.py
```
*Este comando irá mapear os arquivos no servidor, efetuar o download dos ZIPs em paralelo (até 4 por vez) e depois extraí-los para a pasta `data/extraido/`, apagando o ZIP original para otimizar espaço.*

#### 3. Executar o processamento ETL (Silver e Gold)
```bash
python build_mei_dataset.py
```
*Este comando converte os CSVs brutos em parquets compactados na camada Silver em lotes eficientes e depois gera a tabela Fato consolidada `data/parquets/mei_estabelecimentos_YYYYMMDD.parquet`.*

#### 4. Subir o contêiner do MongoDB
```bash
# Iniciar MongoDB no Docker
docker run -d --name mongo-local -p 27017:27017 -v mongo_data:/data/db mongo:latest
```

#### 5. Executar a importação para o MongoDB (Operational Layer)
```bash
python integrate_mongodb.py
```
*Lê o Parquet Gold mais recente, cria os documentos estruturados denormalizados, limpa o banco de dados `cnpj_rf` anterior e carrega os novos dados, finalizando com a criação de índices rápidos.*

#### 6. Executar o Dashboard Streamlit
```bash
# Entrar na pasta do dashboard e rodar
cd dashboard
streamlit run app.py
```
Acesse o painel abrindo `http://localhost:8501/` no seu navegador de internet.

---
**Desenvolvido para fins acadêmicos e analíticos de Big Data — 2026.**
