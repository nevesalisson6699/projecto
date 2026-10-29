# 📽️ Painel de Controle Inteligente do Projetor (Android ADB)

Painel web moderno, responsivo e com suporte a arquitetura híbrida (Cloudflare Pages + Backend Flask + ADB local ou remoto via Tailscale / Render).

---

## 🏗️ Arquitetura de Nuvem e Acesso Remoto

Quando hospedado em serviços estáticos na nuvem (como o **Cloudflare Pages**), o front-end HTML/JS não possui acesso direto à sua rede local privada (`192.168.253.112`) nem executa Python. Para resolver isso, o projeto suporta duas soluções integradas:

```
┌─────────────────────────────────┐
│     Cloudflare Pages (HTTPS)     │
│   (https://projecto.pages.dev)  │
└────────────────┬────────────────┘
                 │ fetch() com CORS liberado
                 ▼
┌────────────────────────────────────────────────────────┐
│ OPÇÃO 1: Cloudflare Tunnel / Ngrok / Render (HTTPS)    │
│ OPÇÃO 2: Tailscale Mesh VPN (IP 100.x.x.x:5050)         │
└────────────────┬───────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────┐
│     Backend Flask (app.py)      │
│  (No seu PC ou Render Docker)   │
└────────────────┬────────────────┘
                 │ adb connect
                 ▼
┌─────────────────────────────────┐
│     Projetor Android (ADB)      │
│  (192.168.253.112 ou Tailscale) │
└─────────────────────────────────┘
```

---

### Solução A: Cloudflare Pages + Cloudflare Tunnel (Recomendado & Gratuito)
Esta opção mantém o backend rodando no seu computador (com acesso direto ao ADB do projetor) e gera uma URL pública HTTPS criptografada:

1. Inicie o servidor local: Dê dois cliques em `iniciar_painel.bat`.
2. Em outro terminal, execute `iniciar_tunnel_cloudflare.bat` (ou execute `npx cloudflared tunnel --url http://localhost:5050`).
3. O Cloudflare gerará uma URL HTTPS temporária gratuita (ex: `https://palavra-aleatoria.trycloudflare.com`).
4. Abra seu painel no **Cloudflare Pages**, clique no ícone de engrenagem ⚙️ no canto superior direito, cole a URL gerada e clique em **Salvar**.
5. O painel ficará imediatamente **Online** de qualquer lugar do mundo!

---

### Solução B: Rede Mesh com Tailscale (IPs 100.x.x.x)
Se você utiliza **Tailscale**:

1. Adicione seu computador e/ou o projetor à sua rede Tailscale.
2. Defina a variável `PROJECTOR_IP` no `.env` com o IP do Tailscale (ex: `PROJECTOR_IP=100.85.120.45`).
3. Acesse o painel pelo seu celular no mesmo Tailnet apontando a API para `http://100.x.x.x:5050`.

---

### Solução C: Deploy do Backend no Render / Railway (Docker com ADB)
O repositório já inclui `Dockerfile`, `render.yaml` e `railway.json`:

1. No painel do **Render** (render.com) ou **Railway** (railway.app), crie um novo **Web Service** conectado a este repositório no GitHub.
2. O serviço detectará automaticamente o `Dockerfile`, instalando o Python, Flask e as ferramentas oficiais do Android ADB (`android-tools-adb`).
3. Nas variáveis de ambiente do serviço, configure:
   - `PROJECTOR_IP`: IP público, Tailscale ou rota VPN do projetor.
   - `PORT`: `5050`
4. Use a URL HTTPS gerada (ex: `https://projector-api.onrender.com`) no botão ⚙️ do Cloudflare Pages.

---

## 📁 Estrutura do Projeto

```text
projetor/
├── config.py                 # Configurações de rede, portas e catálogo de apps
├── app.py                    # API Flask com suporte completo a CORS
├── index.html                # Ponto de entrada estático para o Cloudflare Pages
├── public/
│   └── index.html            # Cópia estática para diretório de build
├── templates/
│   └── index.html            # Template servido pelo Flask local
├── Dockerfile                # Imagem Docker com Python 3.11 + ADB nativo
├── render.yaml               # Arquivo de infraestrutura como código para Render
├── railway.json              # Configuração para deploy no Railway
├── Procfile                  # Entrada Gunicorn para PaaS
├── requirements.txt          # flask, flask-cors, gunicorn
├── iniciar_painel.bat         # Inicializador local (Windows)
├── iniciar_tunnel_cloudflare.bat # Túnel HTTPS gratuito com Cloudflare Tunnel
└── README.md                 # Esta documentação
```

---

## 📡 Rotas da API (com CORS Ativo)

| Rota | Método | Descrição |
| :--- | :--- | :--- |
| `/status` | `GET` | Retorna status online/offline, IP e tela atual |
| `/app/<app_name>` | `POST/GET` | Dispara a abertura de apps no projetor |
| `/api/apps` | `GET` | Lista todos os apps cadastrados |
| `/home` | `POST/GET` | Retorna para a tela inicial (`KEYCODE_HOME`) |
| `/voltar` | `POST/GET` | Retorna à tela anterior (`KEYCODE_BACK`) |
| `/cima`, `/baixo`, `/esquerda`, `/direita` | `POST/GET` | Navegação direcional do D-pad |
| `/ok` | `POST/GET` | Confirmação (`KEYCODE_DPAD_CENTER`) |
| `/vol_up`, `/vol_down`, `/mute` | `POST/GET` | Controles de áudio |
| `/power` | `POST/GET` | Desliga / suspende a tela |
| `/otimizar` | `POST/GET` | Limpeza de processos de segundo plano (`am kill-all`) |
