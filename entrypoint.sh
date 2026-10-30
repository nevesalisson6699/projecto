#!/bin/sh
# Sobe o Tailscale em modo userspace dentro do container e inicia o backend do painel.
set -e

: "${TS_AUTHKEY:?Defina TS_AUTHKEY (chave de autenticação do Tailscale) nas variáveis de ambiente}"
: "${API_TOKEN:?Defina API_TOKEN (senha do painel) nas variáveis de ambiente}"

mkdir -p /var/run/tailscale "$HOME/.android"

# Chave ADB fixa (opcional): sem ela, cada container novo gera uma chave e o projetor
# mostra "Permitir depuração?" na tela até alguém aceitar com "Sempre permitir".
if [ -n "$ADB_KEY_B64" ]; then
  echo "$ADB_KEY_B64" | base64 -d > "$HOME/.android/adbkey"
  chmod 600 "$HOME/.android/adbkey"
fi

# 1. Daemon sem placa TUN; estado em memória (com chave efêmera o nó some do tailnet ao desligar)
tailscaled --tun=userspace-networking --state=mem: \
  --socket=/var/run/tailscale/tailscaled.sock \
  --socks5-server=localhost:1055 --outbound-http-proxy-listen=localhost:1055 &

i=0
until [ -S /var/run/tailscale/tailscaled.sock ] || [ $i -ge 30 ]; do i=$((i+1)); sleep 1; done

# 2. Autentica no tailnet
tailscale up --authkey="$TS_AUTHKEY" --hostname="${TS_HOSTNAME:-painel-cloud-relay}" --accept-routes
tailscale ip -4 || true

# 3. O ADB alcança 100.x por socat + 'tailscale nc' (criado sob demanda em discovery.serial)
adb start-server

# 4. Backend (python app.py inicia também a thread de auto-descoberta)
exec python app.py
