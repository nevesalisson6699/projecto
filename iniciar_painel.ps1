# Inicia o painel Flask com codificação UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -Path $PSScriptRoot

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "   PAINEL DE CONTROLE INTELIGENTE DO PROJETOR ADB" -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

python app.py

