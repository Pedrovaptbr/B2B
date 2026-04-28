# Use a imagem oficial do Python como base
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Define variáveis de ambiente para Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia o arquivo de dependências
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do projeto para o diretório de trabalho
COPY . .

# Garante que o script de inicialização tenha permissão de execução (boa prática)
RUN chmod +x /app/run.sh

# Expõe a porta que o gunicorn irá usar
EXPOSE 8000

# --- CORREÇÃO DEFINITIVA ---
# Define o comando para iniciar a aplicação de forma explícita,
# chamando o interpretador de shell para executar o script.
# Isso evita problemas de permissão de arquivo.
CMD ["/bin/bash", "/app/run.sh"]
