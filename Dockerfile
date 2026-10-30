FROM python:3.11-slim

# ADB oficial + socat (ponte TCP do ADB para o Tailscale em modo userspace)
RUN apt-get update && apt-get install -y --no-install-recommends \
    android-tools-adb \
    socat \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Binários oficiais do Tailscale (método recomendado pela Tailscale para containers sem TUN)
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscaled /usr/local/bin/tailscale /usr/local/bin/

WORKDIR /app

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o código da aplicação
COPY . .
RUN chmod +x entrypoint.sh

# Na nuvem o projetor é alcançado só pelo Tailscale: sem varredura de LAN nem ARP
ENV PORT=5050 \
    HOST=0.0.0.0 \
    PROJECTOR_IP=100.123.35.13 \
    PROJECTOR_TAILSCALE_IP=100.123.35.13 \
    PROJECTOR_PORT=5555 \
    LAN_SUBNET= \
    PROJECTOR_MAC= \
    TS_USERSPACE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 5050

CMD ["./entrypoint.sh"]
