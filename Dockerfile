FROM python:3.12-slim

# Evita que o Python gere arquivos .pyc no docker e garante log em tempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Sao_Paulo \
    ODBCSYSINI=/etc \
    ODBCINI=/etc/odbc.ini

WORKDIR /app

# A porta real é definida por IMPORTS_API_PORT no .env e usada pelo Uvicorn.
# Não há EXPOSE fixo porque o compose usa network_mode: host.

# Instala dependências do sistema e Drivers ODBC (aproveita cache se dependências não mudarem)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    g++ \
    tzdata \
    procps \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-archive-keyring.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as dependências Python (camada separada para cache do pip)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Garante a existência das pastas de trabalho base
RUN mkdir -p imports output logs

# Copia o restante do código da aplicação
COPY . .

# Define o comando de inicialização
CMD ["python3", "main.py"]
