# 📽️ Painel de Controle Inteligente do Projetor (Android ADB)

Painel web moderno, responsivo e autônomo para controle remoto de projetor Android via rede Wi-Fi / Ethernet utilizando ADB (Android Debug Bridge).

---

## 🚀 Funcionalidades

1. **Controle Remoto Digital (D-Pad)**:
   - Navegação: Cima, Baixo, Esquerda, Direita e OK (Centro).
   - Ações de Sistema: Voltar (`KEYCODE_BACK`), Início (`KEYCODE_HOME`), Menu (`KEYCODE_MENU`), Power (`KEYCODE_POWER`).
   - Multimídia: Volume +, Volume -, Mudo (`KEYCODE_VOLUME_MUTE`).
2. **Inicialização Direta de Aplicativos (App Launcher)**:
   - Disparo rápido de aplicativos instalados no projetor com 1 clique (YouTube, Netflix, Prime Video, YouCine, Chrome, UniTV, Ajustes e Início) via eventos de intent ADB (`monkey -p <pacote>`).
3. **Otimização e Limpeza de Memória RAM**:
   - Botão dedicado para executar `am kill-all`, finalizando processos inativos em segundo plano e aliviando o ZRAM/swap em dispositivos de 1 GB de RAM.
4. **Monitoramento em Tempo Real**:
   - Status visual de conexão (*Online / Offline*) com checagem automática e reconexão transparente caso a rede oscile.
   - Identificação dinâmica do aplicativo ou tela ativa no projetor.
5. **Responsividade e Usabilidade**:
   - Interface com tema escuro (Dark Glassmorphism) otimizada para telas de celulares e tablets.
   - Requisições assíncronas via `fetch` (sem recarregar a página).
   - Feedback tátil com vibração em smartphones compatíveis e notificações *toast*.
   - Suporte a atalhos de teclado no computador (Setas, Enter, Esc, H, +, -).

---

## 📁 Estrutura do Projeto

```text
projetor/
├── config.py             # Configurações centralizadas (IPs, portas, apps, binário ADB)
├── app.py                # Servidor backend Flask e rotas da API
├── templates/
│   └── index.html        # Interface web responsiva e interativa
├── requirements.txt      # Dependências Python (Flask)
├── .env.example          # Modelo de variáveis de ambiente
├── iniciar_painel.bat     # Inicializador rápido para Windows (1-clique)
├── iniciar_painel.ps1    # Script PowerShell de inicialização
└── README.md             # Documentação do projeto
```

---

## ⚙️ Pré-requisitos

1. **Python 3.10+** instalado.
2. **Android Platform Tools (ADB)**:
   - O projeto detecta automaticamente o executável `adb.exe` no PATH do sistema, na pasta de Downloads ou nos diretórios padrão do Android SDK.
3. Projetor conectado na mesma rede local e com a **Depuração USB / ADB over Network** habilitada no IP padrão `192.168.253.112:5555`.

---

## 🛠️ Instalação e Execução

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Iniciar o Servidor
* **No Windows (Mais fácil)**: Dê um duplo-clique no arquivo `iniciar_painel.bat`.
* **Via terminal**:
```bash
python app.py
```

### 3. Acessar o Painel
* **Neste computador**: `http://localhost:5050`
* **Pelo celular (na mesma rede Wi-Fi)**: `http://<IP_DO_COMPUTADOR>:5050` (ex: `http://192.168.253.108:5050`)

---

## 📡 Rotas da API

| Rota | Método | Descrição |
| :--- | :--- | :--- |
| `/` | `GET` | Carrega a interface web do controle remoto |
| `/status` | `GET` | Retorna o status da conexão ADB e o app ativo |
| `/app/<app_name>` | `GET/POST` | Inicia um aplicativo no projetor (ex: `/app/youtube`) |
| `/api/apps` | `GET` | Lista todos os aplicativos mapeados em JSON |
| `/home` | `GET/POST` | Retorna para a tela inicial (`KEYCODE_HOME`) |
| `/voltar` | `GET/POST` | Retorna à tela anterior (`KEYCODE_BACK`) |
| `/cima`, `/baixo`, `/esquerda`, `/direita` | `GET/POST` | Teclas direcionais do D-pad |
| `/ok` | `GET/POST` | Confirmação / Enter (`KEYCODE_DPAD_CENTER`) |
| `/vol_up`, `/vol_down`, `/mute` | `GET/POST` | Controles de volume e áudio |
| `/power` | `GET/POST` | Ligar / Desligar / Suspender tela |
| `/otimizar` ou `/limpar` | `GET/POST` | Executa limpeza de RAM (`am kill-all`) |
| `/api/cmd/<comando>` | `GET/POST` | Rota genérica para qualquer tecla ou comando |

---

## ⌨️ Atalhos de Teclado no PC

* **Setas (↑, ↓, ←, →)**: Navegação do D-pad
* <kbd>Enter</kbd>: OK / Selecionar
* <kbd>Esc</kbd> ou <kbd>Backspace</kbd>: Voltar
* <kbd>H</kbd>: Tela Inicial (Home)
* <kbd>+</kbd> ou <kbd>=</kbd>: Aumentar Volume
* <kbd>-</kbd> ou <kbd>_</kbd>: Diminuir Volume
* <kbd>O</kbd>: Otimizar Memória RAM

