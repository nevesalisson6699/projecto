# 📽️ Painel de Controle Inteligente do Projetor (Android ADB)

Painel web moderno e responsivo (Backend Flask + WebSocket em Tempo Real + Touchpad + Teclado Virtual Inteligente).

> 🔒 **Somente rede local.** O painel e a API só respondem a dispositivos na mesma rede do PC/projetor (IPs privados). Acessos pela internet, Tailscale ou outros sites são recusados com HTTP 403.

---

## ✨ Recursos Avançados

1. **Acesso na Mesma Rede**:
   - Rode `python app.py` (ou `iniciar_painel.bat`) no PC e abra `http://IP-DO-PC:5050` no celular conectado ao mesmo Wi-Fi.
   - O projetor é encontrado sozinho (último IP → MAC na tabela ARP → varredura da sub-rede `LAN_SUBNET`).
   - Se precisar, force o IP do projetor em **⚙️ Conexão Manual**.

2. **Teclado Virtual Inteligente (QWERTY & Numérico)**:
   - Alternância entre layout **QWERTY (Letras)** e **123 (Numérico / PIN)**.
   - Digitação em tempo real no campo focado da tela do projetor.
   - Barra de envio de textos completos ou links via `adb input text`.
   - Teclas de controle dedicadas: Backspace (⌫), Espaço (␣) e Ir / Enter (⏎).

3. **Modo Touchpad Avançado (Mouse / Cursor)**:
   - Superfície tátil sensível ao toque para arrastar o cursor livremente na tela (1280x720).
   - Suporte a toques secos (clique esquerdo) e gestos de arraste (*swipe*).
   - Botões físicos virtuais: Clique Esquerdo, Botão Voltar (Cancelar) e Rolagem vertical (Scroll Cima / Scroll Baixo).

4. **Navegação por Abas (Mobile First)**:
   - 📱 **Controle**: D-pad ergonômico, botões de sistema (Power, Mute, Menu, Voltar, Home), volume e otimização de RAM (`am kill-all`).
   - 📺 **Apps**: Abertura em 1 clique dos apps (YouTube, Netflix, Prime Video, YouCine, Chrome, UniTV, Ajustes e Início).
   - 🖱️ **Touchpad**: Modo mouse completo.
   - ⌨️ **Teclado**: Digitação inteligente.
   - ⚡ **Extras**: Otimização profunda e captura de tela do projetor.
   - Efeito visual ripple e vibração tátil leve (`navigator.vibrate(25)`).

---

## 📁 Estrutura de Arquivos

```text
projetor/
├── config.py                 # Configurações de rede, portas e catálogo de apps
├── app.py                    # API Flask + WebSocket (Socket.IO), acesso só da rede local
├── discovery.py              # Auto-descoberta do projetor na LAN
├── templates/
│   └── index.html            # Template com Abas, D-pad, Touchpad e Teclado
├── requirements.txt          # flask, flask-socketio
├── iniciar_painel.bat         # Inicializador local (Windows)
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
| `/app/<app_name>` | `POST/GET` | Dispara a inicialização de aplicativos |
| `/otimizar` | `POST/GET` | Executa `am kill-all` para liberar memória RAM |
| `WS send_command` | Socket.IO | Envia comando de navegação em tempo real |
| `WS touchpad_motion`| Socket.IO | Movimentação do ponteiro em tempo real |
