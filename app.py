import os
import re
import subprocess
import socket
import threading
import time
import base64
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from config import (
    get_projector_ip,
    set_projector_ip,
    get_projector_target,
    PROJECTOR_PORT,
    SERVER_HOST,
    SERVER_PORT,
    DEBUG_MODE,
    ADB_BIN,
    KEYCODES,
    APPS
)

app = Flask(__name__, static_folder="static", template_folder="templates")

# Habilita CORS completo em todas as rotas (Cloudflare Pages, etc)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Servidor WebSocket em tempo real para comunicação com o front-end na nuvem
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Posição virtual do cursor (Resolução nativa 1280x720)
cursor_state = {"x": 640, "y": 360}

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, X-Projector-IP"
    return response

def resolve_target(custom_ip_or_target: str = None) -> str:
    """Resolve dinamicamente o IP/alvo do projetor (IP:PORTA), priorizando o enviado na requisição."""
    raw = custom_ip_or_target
    if not raw:
        try:
            # 1. Header HTTP customizado enviado pelo front-end
            raw = request.headers.get("X-Projector-IP")
            # 2. Parâmetro de query string ?ip=...
            if not raw:
                raw = request.args.get("ip")
            # 3. Corpo JSON da requisição
            if not raw and request.is_json:
                data = request.get_json(silent=True)
                if isinstance(data, dict):
                    raw = data.get("ip")
            # 4. Formulário POST
            if not raw and request.form:
                raw = request.form.get("ip")
        except RuntimeError:
            # Fora do contexto de requisição HTTP (ex: inicialização ou thread independente)
            pass

    if raw and str(raw).strip():
        cleaned = str(raw).strip()
        # Remove protocolos http/https e barras residuais caso o usuário envie URL completa
        cleaned = re.sub(r'^https?://', '', cleaned).split('/')[0]
        if ":" not in cleaned:
            target = f"{cleaned}:{PROJECTOR_PORT}"
        else:
            target = cleaned
        # Atualiza a memória de último IP conhecido
        ip_only = target.split(":")[0]
        set_projector_ip(ip_only)
        return target

    return get_projector_target()

def run_adb(args: list[str], target: str = None, timeout: int = 8) -> tuple[bool, str]:
    """Executa um comando ADB diretamente no projetor de forma dinâmica e segura."""
    resolved = resolve_target(target)
    cmd = [ADB_BIN, "-s", resolved] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = (res.stdout or res.stderr).strip()
        # Se falhou por desconexão no IP alvo, tenta auto-conectar e repete o comando
        if res.returncode != 0 and any(err in output.lower() for err in ["not found", "offline", "device none", "no devices"]):
            connect_projector(custom_target=resolved)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            output = (res.stdout or res.stderr).strip()
        return res.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"Timeout de comunicação com {resolved} via ADB."
    except Exception as e:
        return False, f"Erro ADB ({resolved}): {str(e)}"

def connect_projector(custom_target: str = None) -> tuple[bool, str]:
    """Conecta dinamicamente ao IP do projetor via ADB."""
    resolved = resolve_target(custom_target)
    try:
        res = subprocess.run([ADB_BIN, "connect", resolved], capture_output=True, text=True, timeout=8)
        out = (res.stdout or res.stderr).strip()
        success = "connected to" in out.lower() or "already connected" in out.lower()
        return success, out
    except Exception as e:
        return False, str(e)

def get_current_app(target: str = None) -> str:
    """Detecta o aplicativo atualmente visível na tela do projetor no IP alvo."""
    resolved = resolve_target(target)
    ok, out = run_adb(["shell", "dumpsys", "window", "displays"], target=resolved)
    if not ok:
        ok, out = run_adb(["shell", "dumpsys", "window"], target=resolved)
    
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            for key, app_data in APPS.items():
                if app_data["package"] in line:
                    return app_data["name"]
            if "/" in line:
                try:
                    pkg_part = line.split("/")[0].split()[-1]
                    return pkg_part
                except Exception:
                    pass
    return "Área Inicial"

def get_projector_status(target: str = None) -> dict:
    """Verifica a conectividade e os parâmetros de saúde do projetor dinamicamente."""
    resolved = resolve_target(target)
    ip = resolved.split(":")[0]
    
    success, state_out = run_adb(["get-state"], target=resolved, timeout=4)
    is_online = success and "device" in state_out.lower()
    
    if not is_online:
        conn_ok, _ = connect_projector(custom_target=resolved)
        if conn_ok:
            success, state_out = run_adb(["get-state"], target=resolved, timeout=4)
            is_online = success and "device" in state_out.lower()
            
    current_app = "Desconectado"
    if is_online:
        current_app = get_current_app(target=resolved)

    return {
        "status": "online" if is_online else "offline",
        "ip": ip,
        "target": resolved,
        "current_app": current_app,
        "cursor": cursor_state,
        "details": state_out if is_online else "Não conectado"
    }

FEEDBACK_HTML_CONTENT = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Feedback</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body {
    width: 100%;
    height: 100%;
    background: rgba(10, 15, 30, 0.90);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #ffffff;
    overflow: hidden;
  }
  .card {
    background: linear-gradient(145deg, #1e293b, #0f172a);
    border: 2px solid #38bdf8;
    box-shadow: 0 25px 60px rgba(0,0,0,0.85), 0 0 45px rgba(56, 189, 248, 0.4);
    border-radius: 28px;
    padding: 38px 64px;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    min-width: 480px;
    animation: zoomIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes zoomIn {
    from { transform: scale(0.75); opacity: 0; }
    to { transform: scale(1); opacity: 1; }
  }
  .badge {
    width: 84px;
    height: 84px;
    background: rgba(34, 197, 94, 0.18);
    border: 3px solid #22c55e;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 22px;
    box-shadow: 0 0 30px rgba(34, 197, 94, 0.5);
  }
  .badge svg {
    width: 46px;
    height: 46px;
    stroke: #22c55e;
    stroke-width: 3.5;
    fill: none;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .msg-title {
    font-size: 44px;
    font-weight: 800;
    color: #f8fafc;
    margin-bottom: 10px;
    letter-spacing: -0.5px;
    text-shadow: 0 2px 12px rgba(0,0,0,0.6);
  }
  .msg-sub {
    font-size: 22px;
    font-weight: 600;
    color: #38bdf8;
    margin-bottom: 28px;
  }
  .btn-close {
    background: linear-gradient(135deg, #0284c7, #2563eb);
    color: #ffffff;
    font-size: 22px;
    font-weight: 700;
    padding: 14px 44px;
    border: none;
    border-radius: 16px;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(2, 132, 199, 0.45);
    outline: none;
    transition: all 0.2s;
  }
  .btn-close:focus, .btn-close:hover {
    transform: scale(1.06);
    background: linear-gradient(135deg, #38bdf8, #3b82f6);
    box-shadow: 0 8px 25px rgba(56, 189, 248, 0.6);
  }
  .timer-bar {
    width: 100%;
    height: 6px;
    background: rgba(255, 255, 255, 0.12);
    border-radius: 4px;
    margin-top: 26px;
    overflow: hidden;
  }
  .timer-fill {
    height: 100%;
    width: 100%;
    background: linear-gradient(90deg, #38bdf8, #22c55e);
    animation: countdown 3.0s linear forwards;
  }
  @keyframes countdown {
    from { width: 100%; }
    to { width: 0%; }
  }
</style>
</head>
<body>
<div class="card">
  <div class="badge">
    <svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"></polyline></svg>
  </div>
  <div class="msg-title">Executado, Acunha!!!</div>
  <div class="msg-sub">Otimizações & Sistema Atualizados com Sucesso</div>
  <button id="closeBtn" class="btn-close" autofocus onclick="dismiss()">Fechar [OK]</button>
  <div class="timer-bar">
    <div class="timer-fill"></div>
  </div>
</div>
<script>
  function dismiss() {
    try { window.close(); } catch(e) {}
    try { history.back(); } catch(e) {}
  }
  document.addEventListener("keydown", function(e) {
    dismiss();
  });
  setTimeout(dismiss, 3000);
</script>
</body>
</html>"""

_last_feedback_time = 0
_feedback_lock = threading.Lock()

def trigger_projector_feedback(target: str = None, message: str = "Executado, acunha!", force_dialog: bool = True):
    """
    Dispara feedback visual na tela grande do projetor Android via ADB:
    1. Notificação nativa via 'cmd notification post'
    2. Janela/diálogo flutuante na UI do Android com botão 'Fechar' e auto-close de 3 segundos
    Executado em thread assíncrona para manter a resposta da API instantânea.
    """
    global _last_feedback_time
    resolved = resolve_target(target)

    def _worker():
        global _last_feedback_time
        try:
            # 1. Notificação nativa do sistema Android
            notif_cmd = [
                "shell", "su", "2000", "cmd", "notification", "post",
                "-S", "bigtext",
                "-t", "Painel do Projetor",
                "painel_feedback",
                message
            ]
            run_adb(notif_cmd, target=resolved)

            # Evita colisões se outro diálogo foi aberto recentemente
            now = time.time()
            with _feedback_lock:
                if now - _last_feedback_time < 3.2 and not force_dialog:
                    return
                _last_feedback_time = now

            # 2. Garante que o arquivo HTML de feedback existe no projetor
            check_ok, _ = run_adb(["shell", "test", "-f", "/data/local/tmp/feedback.html"], target=resolved)
            if not check_ok:
                b64 = base64.b64encode(FEEDBACK_HTML_CONTENT.encode("utf-8")).decode("ascii")
                write_cmd = [
                    "shell",
                    f'echo "{b64}" | base64 -d > /data/local/tmp/feedback.html && chmod 666 /data/local/tmp/feedback.html'
                ]
                run_adb(write_cmd, target=resolved)

            # 3. Abre o diálogo flutuante na UI do Android
            view_cmd = [
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", "file:///data/local/tmp/feedback.html",
                "-t", "text/html",
                "com.android.htmlviewer/.HTMLViewerActivity"
            ]
            run_adb(view_cmd, target=resolved)

            # 4. Aguarda 3.2s para exibição fluida e fecha com segurança
            time.sleep(3.2)
            run_adb(["shell", "am", "force-stop", "com.android.htmlviewer"], target=resolved)
        except Exception as e:
            print(f"[-] Erro ao disparar feedback no projetor: {e}")

    threading.Thread(target=_worker, daemon=True).start()

def execute_remote_command(cmd_name: str, target: str = None) -> dict:
    """Dispara eventos de tecla física do controle remoto no IP dinâmico."""
    resolved = resolve_target(target)
    cmd_clean = cmd_name.lower().strip()

    if cmd_clean in ["limpar", "otimizar", "kill_all"]:
        success, out = run_adb(["shell", "am", "kill-all"], target=resolved)
        if success:
            trigger_projector_feedback(target=resolved, message="Executado, acunha!", force_dialog=True)
        return {
            "status": "success" if success else "error",
            "command": cmd_clean,
            "target": resolved,
            "message": "Memória RAM otimizada e processos em segundo plano finalizados!" if success else f"Falha na otimização: {out}",
            "raw": out
        }

    if cmd_clean not in KEYCODES:
        return {
            "status": "error",
            "command": cmd_clean,
            "target": resolved,
            "message": f"Comando '{cmd_clean}' não reconhecido."
        }

    keycode = KEYCODES[cmd_clean]
    success, out = run_adb(["shell", "input", "keyevent", str(keycode)], target=resolved)
    if success and cmd_clean in ["power", "menu", "home"]:
        trigger_projector_feedback(target=resolved, message="Executado, acunha!", force_dialog=False)

    return {
        "status": "success" if success else "error",
        "command": cmd_clean,
        "keycode": keycode,
        "target": resolved,
        "message": f"Tecla {cmd_clean.upper()} acionada com sucesso em {resolved}." if success else f"Erro ao enviar tecla: {out}"
    }

def launch_app(app_key_or_package: str, target: str = None) -> dict:
    """Inicia um aplicativo no projetor via intent / monkey no IP dinâmico."""
    resolved = resolve_target(target)
    key = app_key_or_package.lower().strip()
    if key in APPS:
        package = APPS[key]["package"]
        app_name = APPS[key]["name"]
    else:
        package = app_key_or_package.strip()
        app_name = package

    cmd = ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]
    success, out = run_adb(cmd, target=resolved)
    if success:
        trigger_projector_feedback(target=resolved, message="Executado, acunha!", force_dialog=True)

    return {
        "status": "success" if success else "error",
        "app": app_name,
        "package": package,
        "target": resolved,
        "message": f"Iniciando {app_name} em {resolved}..." if success else f"Falha ao iniciar {app_name}: {out}",
        "raw": out
    }

def send_text_to_projector(text: str, target: str = None) -> dict:
    """Envia texto completo para digitação no campo ativo do Android."""
    resolved = resolve_target(target)
    if not text:
        return {"status": "error", "message": "Texto vazio."}

    escaped = text.replace(" ", "%s")
    escaped = re.sub(r'([\\`"\';|&<>$()])', r'\\\1', escaped)

    success, out = run_adb(["shell", "input", "text", escaped], target=resolved)
    if success:
        trigger_projector_feedback(target=resolved, message="Executado, acunha!", force_dialog=False)
    return {
        "status": "success" if success else "error",
        "action": "input_text",
        "target": resolved,
        "text": text,
        "message": f"Texto digitado em {resolved}: {text}" if success else f"Erro ao digitar: {out}"
    }

def send_key_char(char_or_code: str, target: str = None) -> dict:
    """Envia uma tecla individual (teclado virtual) para o IP do projetor."""
    resolved = resolve_target(target)
    val = str(char_or_code).strip()
    if not val:
        return {"status": "error", "message": "Caractere inválido."}

    special_keys = {
        "backspace": "67",  # KEYCODE_DEL
        "del": "67",
        "enter": "66",      # KEYCODE_ENTER
        "space": "62",      # KEYCODE_SPACE
        "tab": "61",        # KEYCODE_TAB
        "search": "84",     # KEYCODE_SEARCH
    }

    low = val.lower()
    if low in special_keys:
        keycode = special_keys[low]
        success, out = run_adb(["shell", "input", "keyevent", keycode], target=resolved)
        return {"status": "success" if success else "error", "key": low, "keycode": keycode, "target": resolved}

    if val.isdigit() and len(val) > 1 and int(val) in range(1, 300):
        success, out = run_adb(["shell", "input", "keyevent", val], target=resolved)
        return {"status": "success" if success else "error", "keycode": val, "target": resolved}

    if val == " ":
        success, out = run_adb(["shell", "input", "keyevent", "62"], target=resolved)
    else:
        escaped = val.replace(" ", "%s")
        escaped = re.sub(r'([\\`"\';|&<>$()])', r'\\\1', escaped)
        success, out = run_adb(["shell", "input", "text", escaped], target=resolved)

    return {"status": "success" if success else "error", "char": val, "target": resolved}

def handle_touchpad_motion(dx: float, dy: float, target: str = None) -> dict:
    """Atualiza a posição virtual do cursor no projetor."""
    resolved = resolve_target(target)
    global cursor_state
    scale = 1.4
    new_x = max(0, min(1279, int(cursor_state["x"] + dx * scale)))
    new_y = max(0, min(719, int(cursor_state["y"] + dy * scale)))
    cursor_state["x"] = new_x
    cursor_state["y"] = new_y
    return {"status": "success", "cursor": cursor_state, "target": resolved}

def handle_touchpad_tap(x: int = None, y: int = None, target: str = None) -> dict:
    """Executa um clique/toque na tela nas coordenadas especificadas ou no cursor atual."""
    resolved = resolve_target(target)
    global cursor_state
    tap_x = x if x is not None else cursor_state["x"]
    tap_y = y if y is not None else cursor_state["y"]
    success, out = run_adb(["shell", "input", "tap", str(tap_x), str(tap_y)], target=resolved)
    return {"status": "success" if success else "error", "x": tap_x, "y": tap_y, "target": resolved}

def handle_touchpad_swipe(x1: int, y1: int, x2: int, y2: int, duration: int = 200, target: str = None) -> dict:
    """Executa um gesto de arraste (swipe) na tela."""
    resolved = resolve_target(target)
    success, out = run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)], target=resolved)
    return {"status": "success" if success else "error", "message": "Gesto executado.", "target": resolved}

def handle_touchpad_scroll(direction: str, target: str = None) -> dict:
    """Executa rolagem vertical (scroll up / scroll down)."""
    resolved = resolve_target(target)
    if direction == "down":
        return handle_touchpad_swipe(640, 520, 640, 200, 180, target=resolved)
    else:
        return handle_touchpad_swipe(640, 200, 640, 520, 180, target=resolved)

# ----------------- EVENTOS WEBSOCKET (TEMPO REAL) -----------------

@socketio.on("connect")
def ws_connect():
    emit("status_update", get_projector_status())

@socketio.on("ping_status")
def ws_ping_status(data=None):
    target = (data or {}).get("ip") if isinstance(data, dict) else None
    emit("status_update", get_projector_status(target=target))

@socketio.on("set_ip")
def ws_set_ip(data):
    new_ip = data.get("ip", "").strip() if isinstance(data, dict) else ""
    if new_ip:
        target = resolve_target(new_ip)
        connect_projector(custom_target=target)
    st = get_projector_status(target=new_ip)
    socketio.emit("status_update", st)

@socketio.on("send_command")
def ws_send_command(data):
    cmd = data.get("cmd", "")
    target = data.get("ip")
    res = execute_remote_command(cmd, target=target)
    emit("command_response", res)
    if cmd in ["home", "voltar"]:
        socketio.emit("status_update", get_projector_status(target=target))

@socketio.on("send_app")
def ws_send_app(data):
    app_key = data.get("app", "")
    target = data.get("ip")
    res = launch_app(app_key, target=target)
    emit("command_response", res)
    time.sleep(0.8)
    socketio.emit("status_update", get_projector_status(target=target))

@socketio.on("input_text")
def ws_input_text(data):
    txt = data.get("text", "")
    target = data.get("ip")
    res = send_text_to_projector(txt, target=target)
    emit("command_response", res)

@socketio.on("input_key")
def ws_input_key(data):
    val = data.get("key") or data.get("keycode") or data.get("char")
    target = data.get("ip")
    res = send_key_char(val, target=target)
    emit("command_response", res)

@socketio.on("touchpad_motion")
def ws_touchpad_motion(data):
    dx = float(data.get("dx", 0))
    dy = float(data.get("dy", 0))
    target = data.get("ip")
    res = handle_touchpad_motion(dx, dy, target=target)
    emit("cursor_update", res)

@socketio.on("touchpad_tap")
def ws_touchpad_tap(data):
    x = data.get("x")
    y = data.get("y")
    target = data.get("ip")
    res = handle_touchpad_tap(x, y, target=target)
    emit("command_response", res)

@socketio.on("touchpad_scroll")
def ws_touchpad_scroll(data):
    direction = data.get("direction", "down")
    target = data.get("ip")
    res = handle_touchpad_scroll(direction, target=target)
    emit("command_response", res)

@socketio.on("touchpad_click")
def ws_touchpad_click(data):
    btn = data.get("button", "left")
    target = data.get("ip")
    if btn == "right":
        res = execute_remote_command("voltar", target=target)
    else:
        res = handle_touchpad_tap(target=target)
    emit("command_response", res)

@socketio.on("trigger_feedback")
def ws_trigger_feedback(data=None):
    target = (data or {}).get("ip") if isinstance(data, dict) else None
    msg = (data or {}).get("message", "Executado, acunha!") if isinstance(data, dict) else "Executado, acunha!"
    trigger_projector_feedback(target=target, message=msg, force_dialog=True)
    emit("command_response", {"status": "success", "message": msg, "target": resolve_target(target)})

# ----------------- ROTAS REST (COMPATIBILIDADE E FETCH) -----------------

@app.route("/")
def index():
    return render_template("index.html", projector_ip=get_projector_ip(), apps=APPS)

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "projector-adb-api"}), 200

@app.route("/status", methods=["GET", "OPTIONS"])
def status_endpoint():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    return jsonify(get_projector_status())

@app.route("/api/config/ip", methods=["POST", "OPTIONS"])
def route_update_ip():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    
    data = request.get_json(silent=True) or request.form
    new_ip = data.get("ip", "").strip() if data else ""
    if not new_ip:
        return jsonify({"status": "error", "message": "IP não informado."}), 400

    set_projector_ip(new_ip)
    connect_ok, msg = connect_projector()
    st = get_projector_status()
    socketio.emit("status_update", st)
    
    if connect_ok:
        trigger_projector_feedback(target=get_projector_target(), message="Executado, acunha!", force_dialog=True)

    return jsonify({
        "status": "success" if connect_ok else "warning",
        "ip": get_projector_ip(),
        "connected": connect_ok,
        "message": f"IP atualizado para {get_projector_ip()}! ({msg})",
        "details": st
    })

# Rotas de Teclado e Texto
@app.route("/api/input/text", methods=["POST", "OPTIONS"])
def route_input_text():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form
    text = data.get("text", "") if data else ""
    return jsonify(send_text_to_projector(text))

@app.route("/api/input/key", methods=["POST", "OPTIONS"])
def route_input_key():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form
    char_or_code = data.get("key") or data.get("char") or data.get("keycode") if data else ""
    return jsonify(send_key_char(char_or_code))

# Rotas de Touchpad e Mouse
@app.route("/api/touchpad/motion", methods=["POST", "OPTIONS"])
def route_touchpad_motion():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form or {}
    dx = float(data.get("dx", 0))
    dy = float(data.get("dy", 0))
    return jsonify(handle_touchpad_motion(dx, dy))

@app.route("/api/touchpad/tap", methods=["POST", "OPTIONS"])
def route_touchpad_tap():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form or {}
    x = data.get("x")
    y = data.get("y")
    return jsonify(handle_touchpad_tap(x, y))

@app.route("/api/touchpad/swipe", methods=["POST", "OPTIONS"])
def route_touchpad_swipe():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form or {}
    x1 = int(data.get("x1", 640))
    y1 = int(data.get("y1", 360))
    x2 = int(data.get("x2", 640))
    y2 = int(data.get("y2", 360))
    duration = int(data.get("duration", 200))
    return jsonify(handle_touchpad_swipe(x1, y1, x2, y2, duration))

@app.route("/api/touchpad/scroll", methods=["POST", "OPTIONS"])
def route_touchpad_scroll():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form or {}
    direction = data.get("direction", "down")
    return jsonify(handle_touchpad_scroll(direction))

@app.route("/api/touchpad/click", methods=["POST", "OPTIONS"])
def route_touchpad_click():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    data = request.get_json(silent=True) or request.form or {}
    btn = data.get("button", "left")
    if btn == "right":
        return jsonify(execute_remote_command("voltar"))
    return jsonify(handle_touchpad_tap())

# Rotas de Aplicativos
@app.route("/app/<app_name>", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/app/<app_name>", methods=["GET", "POST", "OPTIONS"])
def route_launch_app(app_name):
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    res = launch_app(app_name)
    socketio.emit("status_update", get_projector_status())
    return jsonify(res)

@app.route("/api/apps", methods=["GET", "OPTIONS"])
def route_list_apps():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(APPS)

# Rotas Tailscale (Guia e Telemetria Remota)
@app.route("/api/tailscale/status", methods=["GET", "OPTIONS"])
def route_tailscale_status():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    
    # Checa se o pacote com.tailscale.ipn está instalado
    ok_pkg, out_pkg = run_adb(["shell", "pm", "list", "packages", "com.tailscale.ipn"])
    is_installed = ok_pkg and "com.tailscale.ipn" in out_pkg

    # Checa se há interface com IP na faixa 100.x.x.x
    tailscale_ip = None
    ok_ip, out_ip = run_adb(["shell", "ip", "-o", "addr", "show"])
    if ok_ip:
        for line in out_ip.splitlines():
            if "inet 100." in line:
                parts = line.split()
                for idx, part in enumerate(parts):
                    if part == "inet" and idx + 1 < len(parts):
                        tailscale_ip = parts[idx + 1].split("/")[0]
                        break

    return jsonify({
        "status": "success",
        "installed": is_installed,
        "tailscale_ip": tailscale_ip,
        "active": bool(tailscale_ip)
    })

@app.route("/api/tailscale/open", methods=["POST", "OPTIONS"])
def route_tailscale_open():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    ok, out = run_adb(["shell", "monkey", "-p", "com.tailscale.ipn", "-c", "android.intent.category.LAUNCHER", "1"], target=target)
    if ok:
        trigger_projector_feedback(target=target, message="Executado, acunha!", force_dialog=True)
    return jsonify({
        "status": "success" if ok else "error",
        "message": "Abrindo Tailscale no projetor..." if ok else f"Erro ao abrir Tailscale: {out}",
        "target": target
    })

# Rota de Feedback Visual no Projetor (Executado, Acunha!!!)
@app.route("/api/feedback", methods=["GET", "POST", "OPTIONS"])
def route_feedback():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    trigger_projector_feedback(target=target, message="Executado, Acunha!!!", force_dialog=True)
    return jsonify({
        "status": "success",
        "message": "Executado, Acunha!!!",
        "target": target
    })

# ----------------- NOVAS ROTAS: OTIMIZAÇÃO PROFUNDA, REDE, DISPLAY & UTILS -----------------

@app.route("/otimizar_profundo", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/otimizar_profundo", methods=["GET", "POST", "OPTIONS"])
def route_otimizar_profundo():
    """Aplica otimização extrema de RAM, animações, Wi-Fi e tempo de tela de 60 min no projetor."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()

    commands = [
        # 1. Tempo de tela e inatividade: 60 minutos (3.600.000 ms)
        ["shell", "settings", "put", "system", "screen_off_timeout", "3600000"],
        ["shell", "settings", "put", "secure", "sleep_timeout", "3600000"],
        ["shell", "settings", "put", "secure", "screensaver_enabled", "0"],
        # 2. Desativação total de animações (fluidez imediata)
        ["shell", "settings", "put", "global", "window_animation_scale", "0.0"],
        ["shell", "settings", "put", "global", "transition_animation_scale", "0.0"],
        ["shell", "settings", "put", "global", "animator_duration_scale", "0.0"],
        # 3. Wi-Fi e Bluetooth estabilizados (Sem economia agressiva ou varredura de fundo)
        ["shell", "settings", "put", "global", "wifi_sleep_policy", "2"],
        ["shell", "cmd", "wifi", "set-wifi-saver-enabled", "false"],
        ["shell", "settings", "put", "global", "wifi_scan_always_enabled", "0"],
        ["shell", "settings", "put", "global", "ble_scan_always_enabled", "0"],
        # 4. DNS de Alta Performance (Cloudflare 1.1.1.1)
        ["shell", "settings", "put", "global", "private_dns_mode", "hostname"],
        ["shell", "settings", "put", "global", "private_dns_specifier", "one.one.one.one"],
        # 5. Renderização por Hardware GPU 2D
        ["shell", "setprop", "debug.hwui.renderer", "opengl"],
        ["shell", "settings", "put", "global", "force_gpu_rendering", "1"],
        # 6. Desativar bloatwares/serviços ociosos de fábrica (mantendo Tailscale e sistema intactos)
        ["shell", "pm", "disable-user", "--user", "0", "com.android.dreams.basic"],
        ["shell", "pm", "disable-user", "--user", "0", "com.bozee.usbdisplay"],
        # 7. Limpeza agressiva de cache e processos
        ["shell", "pm", "trim-caches", "999999999999999999"],
        ["shell", "am", "kill-all"],
    ]

    results = []
    for cmd in commands:
        ok, out = run_adb(cmd, target=target, timeout=4)
        results.append({"cmd": " ".join(cmd), "success": ok, "out": out.strip()})

    # Instalação do Projectivy Launcher se o APK estiver baixado
    projectivy_path = os.path.join(os.path.dirname(__file__), "projectivy.apk")
    if os.path.exists(projectivy_path):
        install_ok, install_out = run_adb(["install", "-r", projectivy_path], target=target, timeout=25)
        results.append({"cmd": "install projectivy.apk", "success": install_ok, "out": install_out.strip()})

    # Dispara a tela comemorativa interativa no projetor
    trigger_projector_feedback(target=target, message="Executado, Acunha!!!", force_dialog=True)

    return jsonify({
        "status": "success",
        "message": "Otimização profunda aplicada com sucesso! (Tela: 60min, Animações 0x, Wi-Fi turbo, GPU 2D e Projectivy Launcher)",
        "target": target,
        "results": results
    })

@app.route("/api/cast", methods=["POST", "OPTIONS"])
def route_cast_url():
    """Abre links, streams ou vídeos diretamente no projetor via intent VIEW."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    data = request.get_json(silent=True) or request.form or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"status": "error", "message": "Nenhuma URL informada."}), 400

    # Lança a URL no navegador/app correspondente do projetor
    cmd = ["shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url]
    ok, out = run_adb(cmd, target=target)
    if ok:
        trigger_projector_feedback(target=target, message="Executado, Acunha!!!", force_dialog=False)

    return jsonify({
        "status": "success" if ok else "error",
        "message": f"Abrindo link no projetor: {url}" if ok else f"Falha ao abrir link: {out}",
        "target": target
    })

@app.route("/api/display/brightness", methods=["POST", "OPTIONS"])
def route_set_brightness():
    """Ajusta o nível de brilho do sistema (0 a 255)."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    data = request.get_json(silent=True) or request.form or {}
    val = int(data.get("brightness", 255))
    val = max(10, min(255, val))

    cmd = ["shell", "settings", "put", "system", "screen_brightness", str(val)]
    ok, out = run_adb(cmd, target=target)
    return jsonify({
        "status": "success" if ok else "error",
        "brightness": val,
        "message": f"Brilho ajustado para {val}/255",
        "target": target
    })

@app.route("/api/display/reset_overscan", methods=["POST", "OPTIONS"])
def route_reset_overscan():
    """Restaura o overscan nativo 1:1 e ajusta densidade para nitidez máxima."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    run_adb(["shell", "wm", "overscan", "0,0,0,0"], target=target)
    run_adb(["shell", "wm", "density", "160"], target=target)
    trigger_projector_feedback(target=target, message="Executado, Acunha!!!", force_dialog=True)
    return jsonify({
        "status": "success",
        "message": "Escala nativa 1:1 restaurada com densidade 160 DPI!",
        "target": target
    })

@app.route("/api/display/picture_settings", methods=["POST", "OPTIONS"])
def route_picture_settings():
    """Abre o menu nativo de ajustes de imagem e calibragem do projetor."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()
    # Tenta abrir o menu de configurações do chip de exibição (DroidLogic / HTC)
    ok, out = run_adb(["shell", "monkey", "-p", "com.droidlogic.tv.settings", "-c", "android.intent.category.LAUNCHER", "1"], target=target)
    if not ok:
        ok, out = run_adb(["shell", "am", "start", "-a", "android.settings.DISPLAY_SETTINGS"], target=target)
    return jsonify({
        "status": "success" if ok else "error",
        "message": "Abrindo ajustes de imagem no projetor..." if ok else f"Erro ao abrir ajustes: {out}",
        "target": target
    })

@app.route("/api/screencap", methods=["GET", "POST", "OPTIONS"])
def route_screencap():
    """Captura a tela atual do projetor em tempo real e retorna como base64 PNG."""
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    target = resolve_target()

    # Executa screencap via exec-out para stream binário
    cmd = [ADB_BIN, "-s", target, "exec-out", "screencap", "-p"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
        if proc.returncode == 0 and len(proc.stdout) > 1000:
            b64_img = base64.b64encode(proc.stdout).decode("ascii")
            return jsonify({
                "status": "success",
                "image": f"data:image/png;base64,{b64_img}",
                "target": target
            })
    except Exception as e:
        pass

    return jsonify({"status": "error", "message": "Falha ao capturar tela do projetor."}), 500

# Rota Genérica para Comandos
@app.route("/api/cmd/<command>", methods=["GET", "POST", "OPTIONS"])
def api_command(command):
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command(command))

# Rotas Diretas para Teclas
@app.route("/home", methods=["GET", "POST", "OPTIONS"])
def route_home():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("home"))

@app.route("/voltar", methods=["GET", "POST", "OPTIONS"])
def route_voltar():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("voltar"))

@app.route("/cima", methods=["GET", "POST", "OPTIONS"])
def route_cima():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("cima"))

@app.route("/baixo", methods=["GET", "POST", "OPTIONS"])
def route_baixo():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("baixo"))

@app.route("/esquerda", methods=["GET", "POST", "OPTIONS"])
def route_esquerda():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("esquerda"))

@app.route("/direita", methods=["GET", "POST", "OPTIONS"])
def route_direita():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("direita"))

@app.route("/ok", methods=["GET", "POST", "OPTIONS"])
def route_ok():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("ok"))

@app.route("/vol_up", methods=["GET", "POST", "OPTIONS"])
def route_vol_up():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("vol_up"))

@app.route("/vol_down", methods=["GET", "POST", "OPTIONS"])
def route_vol_down():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("vol_down"))

@app.route("/mute", methods=["GET", "POST", "OPTIONS"])
def route_mute():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("mute"))

@app.route("/power", methods=["GET", "POST", "OPTIONS"])
def route_power():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("power"))

@app.route("/menu", methods=["GET", "POST", "OPTIONS"])
def route_menu():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("menu"))

@app.route("/otimizar", methods=["GET", "POST", "OPTIONS"])
@app.route("/limpar", methods=["GET", "POST", "OPTIONS"])
def route_otimizar():
    if request.method == "OPTIONS": return jsonify({"status": "ok"}), 200
    return jsonify(execute_remote_command("limpar"))

def get_network_ips():
    ips = []
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    return ips

if __name__ == "__main__":
    target = get_projector_target()
    print(f"[*] Conectando ao projetor em {target}...")
    connected, msg = connect_projector()
    if connected:
        print(f"[+] Conectado com sucesso ao projetor em {get_projector_ip()}!")
    else:
        print(f"[-] Aviso na conexão ADB: {msg}")

    network_ips = get_network_ips()
    print("=" * 60)
    print("  PAINEL DE CONTROLE INTELIGENTE DO PROJETOR (WEBSOCKET + REST)")
    print(f"  Alvo ADB Atual : {get_projector_target()}")
    print(f"  Acesso Local   : http://localhost:{SERVER_PORT}")
    for ip in network_ips:
        print(f"  Acesso na Rede : http://{ip}:{SERVER_PORT}")
    print("=" * 60)

    socketio.run(app, host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE, allow_unsafe_werkzeug=True)
