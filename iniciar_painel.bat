@echo off
title Painel de Controle Inteligente do Projetor
chcp 65001 > nul
echo ========================================================
echo   PAINEL DE CONTROLE INTELIGENTE DO PROJETOR ADB
echo ========================================================
echo.
cd /d "%~dp0"
python app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Ocorreu um erro ao iniciar o servidor. Verifique se o Python esta no PATH.
    pause
)

