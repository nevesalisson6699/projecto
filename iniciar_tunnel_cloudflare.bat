@echo off
title Cloudflare Tunnel para Painel do Projetor
chcp 65001 > nul
echo ========================================================
echo   CRIANDO TÚNEL HTTPS SEGURO COM CLOUDFLARE TUNNEL
echo ========================================================
echo.
echo Este script cria um túnel HTTPS gratuito temporário para
echo conectar o Cloudflare Pages diretamente ao seu PC local
echo sem precisar abrir portas no roteador.
echo.
echo Porta local do backend: 5050
echo.
npx --yes cloudflared tunnel --url http://localhost:5050
pause
