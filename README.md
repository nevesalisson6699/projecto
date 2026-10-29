# 📽️ Painel de Controle Inteligente do Projetor (Android ADB)

Painel web moderno, responsivo e com suporte a arquitetura híbrida (Cloudflare Pages + Backend Flask + WebSocket em Tempo Real + Touchpad + Teclado Virtual Inteligente).

---

## ✨ Recursos Avançados

1. **Arquitetura 100% em Nuvem & Acesso Universal**:
   - Front-end estático otimizado para o **Cloudflare Pages** (`https://projecto.pages.dev`).
   - Funciona em qualquer navegador, seja no Wi-Fi, 4G ou 5G.
   - Detecção dinâmica de status *Online/Offline*.
   - **Gerenciamento Dinâmico de IP**: Quando desconectado, exibe um painel interativo para atualizar o IP local, IP Tailscale (`100.x.x.x`) ou URL de túnel com salvamento automático no `localStorage`.

2. **Guia Remoto / Tailscale Integrado**:
   - Tutorial passo a passo ilustrado para conectar o projetor à rede privada WireGuard (Tailscale).
   - Instruções detalhadas para o Projetor (instalação via APK/ADB e login) e Celular (Google Play / App Store).
   - Botão de verificação de status e telemetria do Tailscale em tempo real via ADB (`/api/tailscale/status`).
   - Botão para aplicar o IP `100.x.x.x` detectado com 1 clique direto no painel.

3. **Teclado Virtual Inteligente (QWERTY & Numérico)**:
   - Alternância entre layout **QWERTY (Letras)** e **123 (Numérico / PIN)**.
   - Digitação em tempo real no campo focado da tela do projetor.
   - Barra de envio de textos completos ou links via `adb input text`.
   - Teclas de controle dedicadas: Backspace (⌫), Espaço (␣) e Ir / Enter (⏎).

4. **Modo Touchpad Avançado (Mouse / Cursor)**:
   - Superfície tátil sensível ao toque para arrastar o cursor livremente na tela (1280x720).
   - Suporte a toques secos (clique esquerdo) e gestos de arraste (*swipe*).
   - Botões físicos virtuais: Clique Esquerdo, Botão Voltar (Cancelar) e Rolagem vertical (Scroll Cima / Scroll Baixo).

5. **Navegação por Abas (Mobile First)**:
   - 📱 **Controle**: D-pad ergonômico, botões de sistema (Power, Mute, Menu, Voltar, Home), volume e otimização de RAM (`am kill-all`).
   - 📺 **Apps**: Abertura em 1 clique dos apps (YouTube, Netflix, Prime Video, YouCine, Chrome, UniTV, Ajustes e Início).
   - 🖱️ **Touchpad**: Modo mouse completo.
   - ⌨️ **Teclado**: Digitação inteligente.
   - 🛡️ **Tailscale**: Guia de acesso remoto mundial e status da VPN.
   - Efeito visual ripple e vibração tátil leve (`navigator.vibrate(25)`).

---

## 📁 Estrutura de Arquivos

```text
projetor/
├── config.py                 # Configurações de rede, portas e catálogo de apps
├── app.py                    # API Flask + WebSocket (Socket.IO) com suporte a CORS
├── bridge_agent.py           # Agente local de ponte para servidores na nuvem
├── index.html                # Ponto de entrada estático para o Cloudflare Pages
├── public/
│   └── index.html            # Cópia estática para diretório de build
├── templates/
│   └── index.html            # Template com Abas, D-pad, Touchpad e Teclado
├── Dockerfile                # Imagem Docker com Python 3.11 + ADB nativo
├── render.yaml               # Infraestrutura como código para o Render
├── railway.json              # Configuração para o Railway
├── Procfile                  # Entrada Gunicorn para PaaS
├── requirements.txt          # flask, flask-cors, flask-socketio, gunicorn
├── iniciar_painel.bat         # Inicializador local (Windows)
├── iniciar_tunnel_cloudflare.bat # Túnel HTTPS gratuito via Cloudflare
└── README.md                 # Esta documentação
```

---

## 📡 Rotas da API e WebSocket

| Rota / Evento | Método | Descrição |
| :--- | :--- | :--- |
| `/status` | `GET` | Retorna status online/offline, IP, app e coordenadas do cursor |
| `/api/config/ip` | `POST` | Atualiza o IP alvo do projetor em tempo de execução |
| `/api/input/text` | `POST` | Digita texto completo no campo ativo |
| `/api/input/key` | `POST` | Dispara tecla ou caractere do teclado virtual |
| `/api/touchpad/tap` | `POST` | Executa toque na tela nas coordenadas especificadas |
| `/api/touchpad/swipe`| `POST` | Executa gesto de arraste (swipe) na tela |
| `/api/touchpad/scroll`| `POST` | Executa rolagem vertical (up / down) |
| `/api/touchpad/click`| `POST` | Executa clique esquerdo ou direito |
| `/api/tailscale/status`| `GET` | Retorna se o Tailscale está instalado e o IP 100.x ativo |
| `/api/tailscale/open`| `POST` | Dispara a inicialização do app Tailscale no projetor |
| `/app/<app_name>` | `POST/GET` | Dispara a inicialização de aplicativos |
| `/otimizar` | `POST/GET` | Executa `am kill-all` para liberar memória RAM |
| `WS send_command` | Socket.IO | Envia comando de navegação em tempo real |
| `WS touchpad_motion`| Socket.IO | Movimentação do ponteiro em tempo real |
