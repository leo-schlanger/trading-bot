# Trading Bot Docker Image
# Funciona em qualquer plataforma: x86, ARM (Raspberry Pi), etc.
#
# Build:
#   docker build -t trading-bot -f deploy/docker/Dockerfile .
#
# Run:
#   docker run -d --name trading-bot \
#     -v $(pwd)/data:/app/data \
#     -e TRADING_MODE=paper \
#     -e TELEGRAM_BOT_TOKEN=xxx \
#     -e TELEGRAM_CHAT_ID=xxx \
#     trading-bot

FROM python:3.11-slim

# Argumentos de build
ARG TARGETPLATFORM
ARG BUILDPLATFORM

# Metadados
LABEL maintainer="Trading Bot"
LABEL version="1.0"
LABEL description="Intelligent Trading Bot with ML"

# Variáveis de ambiente
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV BOT_DATA_DIR=/app/data
ENV TRADING_MODE=paper

# Diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primeiro (para cache de layers)
COPY requirements.txt .

# Instalar dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY src/ src/
COPY training/ training/
COPY scripts/ scripts/
COPY config/ config/
COPY run_trading_cycle.py .
COPY run_intelligent_bot.py .
COPY deploy/selfhosted/run_daemon.py deploy/selfhosted/

# Criar diretórios
RUN mkdir -p data/raw data/state data/models logs results

# Volume para persistência
VOLUME ["/app/data", "/app/logs"]

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from src.storage import get_storage; get_storage()" || exit 1

# Comando padrão
CMD ["python", "deploy/selfhosted/run_daemon.py"]
