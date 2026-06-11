import requests
from bs4 import BeautifulSoup
import os
import concurrent.futures  # Biblioteca para gerenciar os downloads simultâneos
import zipfile
import re

# --- CONFIGURAÇÕES ---
BASE_URL = "https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/2025-12-14/"
OUTPUT_DIR = "data/bruto"
MAX_SIMULTANEOS = 4  # Limite de downloads ao mesmo tempo


# Pasta onde estão os arquivos .zip baixados (do passo anterior)
PASTA_ORIGEM = "data/bruto"

# Pasta onde os arquivos descompactados serão salvos
PASTA_DESTINO_BASE = "data/extraido"


# Headers para simular navegador real
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def baixar_arquivo_unico(nome_arquivo):
    """
    Função que será executada por cada 'worker' (thread) individualmente.
    """
    url_completa = BASE_URL + nome_arquivo
    caminho_local = os.path.join(OUTPUT_DIR, nome_arquivo)

    # Verifica se já existe
    if os.path.exists(caminho_local):
        return f"⏭️ [Pular] {nome_arquivo} já existe."

    print(f"⬇️ Iniciando: {nome_arquivo}...")

    try:
        # Timeout de 60s para conexão, mas sem timeout para o download em si
        with requests.get(url_completa, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(caminho_local, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return f"✅ Concluído: {nome_arquivo}"
    
    except Exception as e:
        return f"❌ Erro em {nome_arquivo}: {e}"

def main():
    # 1. Cria a pasta
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 2. Obtém a lista de arquivos
    print("🔎 Mapeando arquivos no servidor...")
    try:
        resp = requests.get(BASE_URL, headers=HEADERS)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erro fatal ao acessar URL: {e}")
        return

    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.find_all('a')

    # Filtra apenas os ZIPS
    arquivos_para_baixar = [
        link.get('href') for link in links 
        if link.get('href') and link.get('href').lower().endswith('.zip')
    ]

    print(f"📋 Total de arquivos encontrados: {len(arquivos_para_baixar)}")
    print(f"🚀 Iniciando downloads (Máximo de {MAX_SIMULTANEOS} simultâneos)...")
    print("-" * 50)

    # 3. Gerenciador de Contexto para Threads
    # O ThreadPoolExecutor gerencia a fila e garante que não passe de 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SIMULTANEOS) as executor:
        
        # Envia todas as tarefas para o pool
        # O dicionário 'future_to_file' mapeia a tarefa ao nome do arquivo (para controle)
        future_to_file = {
            executor.submit(baixar_arquivo_unico, arquivo): arquivo 
            for arquivo in arquivos_para_baixar
        }

        # Conforme as tarefas completam, mostramos o resultado
        for future in concurrent.futures.as_completed(future_to_file):
            nome = future_to_file[future]
            try:
                resultado = future.result()
                print(resultado)
            except Exception as exc:
                print(f"❌ Exceção não tratada em {nome}: {exc}")

    print("-" * 50)
    print("🏁 Todo o processo foi finalizado.")

def extrair_dados():
    # Verifica se a pasta de origem existe
    if not os.path.exists(PASTA_ORIGEM):
        print(f"❌ Erro: A pasta de origem '{PASTA_ORIGEM}' não foi encontrada.")
        return

    # Lista todos os arquivos .zip
    arquivos_zip = [f for f in os.listdir(PASTA_ORIGEM) if f.lower().endswith('.zip')]
    
    if not arquivos_zip:
        print("Nenhum arquivo .zip encontrado para extrair.")
        return

    total = len(arquivos_zip)
    print(f"📂 Encontrados {total} arquivos para extrair. Iniciando...\n")

    for i, nome_arquivo in enumerate(arquivos_zip, 1):
        caminho_completo_zip = os.path.join(PASTA_ORIGEM, nome_arquivo)
        
        # --- Lógica de Criação da Pasta ---
        # 1. Remove a extensão .zip
        nome_sem_extensao = os.path.splitext(nome_arquivo)[0]
        
        # 2. Remove números do final (Ex: "Empresas0" vira "Empresas", "Simples" continua "Simples")
        # A regex '\d+$' busca dígitos apenas no final da string
        nome_categoria = re.sub(r'\d+$', '', nome_sem_extensao)
        
        # 3. Define o caminho da subpasta (ex: dados_extraidos/Empresas)
        caminho_destino_final = os.path.join(PASTA_DESTINO_BASE, nome_categoria)
        
        # Cria a pasta se não existir
        if not os.path.exists(caminho_destino_final):
            os.makedirs(caminho_destino_final)

        print(f"[{i}/{total}] Extraindo '{nome_arquivo}' para a pasta '{nome_categoria}'...")

        try:
            with zipfile.ZipFile(caminho_completo_zip, 'r') as zip_ref:
                # Extrai tudo para a pasta da categoria
                zip_ref.extractall(caminho_destino_final)
                
            # Remove o arquivo .zip de origem após a extração com sucesso
            os.remove(caminho_completo_zip)
            print(f"   ✅ Sucesso e arquivo .zip removido.")
            
        except zipfile.BadZipFile:
            print(f"   ❌ Erro: O arquivo '{nome_arquivo}' parece estar corrompido.")
        except Exception as e:
            print(f"   ❌ Erro desconhecido em '{nome_arquivo}': {e}")

    print("\n🏁 Processo de extração finalizado!")
    print(f"Os arquivos estão em: {os.path.abspath(PASTA_DESTINO_BASE)}")


if __name__ == "__main__":
    main()
    extrair_dados()