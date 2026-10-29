FROM python:3.11-slim

# Instala ferramentas do sistema e o binário ADB oficial
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .

# Variáveis de ambiente padrão
ENV PORT=5050
ENV HOST=0.0.0.0
ENV PROJECTOR_IP=192.168.253.112
ENV PROJECTOR_PORT=5555

EXPOSE 5050

CMD ["sh", "-c", "gunicorn app:app --bind 0.0.0.0:${PORT:-5050}"]
