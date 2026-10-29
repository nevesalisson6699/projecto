import os
import re
import subprocess
import socket
import threading
import time
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

# Habilita CORS completo em todas as rotas
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# Servidor WebSocket em tempo real para comunicação com o front-end na nuvem
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Posição virtual do cursor (Resolução nativa 1280x720)
cursor_state = {"x": 640, "y": 360}

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response

def run_adb(args: list[str], timeout: int = 8) -> tuple[bool, str]:
    """Executa um comando ADB diretamente no projetor de forma segura."""
    target = get_projector_target()
    cmd = [ADB_BIN, "-s", target] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = (res.stdout or res.stderr).strip()
        return res.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timeout de comunicação com o projetor via ADB."
    except Exception as e:
        return False, f"Erro ADB: {str(e)}"

def connect_projector(custom_target: str = None) -> tuple[bool, str]:
    """Conecta ao IP do projetor via ADB."""
    target = custom_target or get_projector_target()
    try:
        res = subprocess.run([ADB_BIN, "connect", target], capture_output=True, text=True, timeout=8)
        out = (res.stdout or res.stderr).strip()
        success = "connected to" in out.lower() or "already connected" in out.lower()
        return success, out
    except Exception as e:
        return False, str(e)

def get_current_app() -> str:
    """Detecta o aplicativo atualmente visível na tela do projetor."""
    ok, out = run_adb(["shell", "dumpsys", "window", "displays"])
    if not ok:
        ok, out = run_adb(["shell", "dumpsys", "window"])
    
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

def get_projector_status() -> dict:
    """Verifica a conectividade e os parâmetros de saúde do projetor."""
    target = get_projector_target()
    ip = get_projector_ip()
    
    success, state_out = run_adb(["get-state"], timeout=4)
    is_online = success and "device" in state_out.lower()
    
    if not is_online:
        conn_ok, _ = connect_projector()
        if conn_ok:
            success, state_out = run_adb(["get-state"], timeout=4)
            is_online = success and "device" in state_out.lower()
            
    current_app = "Desconectado"
    if is_online:
        current_app = get_current_app()

    return {
        "status": "online" if is_online else "offline",
        "ip": ip,
        "target": target,
        "current_app": current_app,
        "cursor": cursor_state,
        "details": state_out if is_online else "Não conectado"
    }

def execute_remote_command(cmd_name: str) -> dict:
    """Dispara eventos de tecla física do controle remoto."""
    cmd_clean = cmd_name.lower().strip()

    if cmd_clean in ["limpar", "otimizar", "kill_all"]:
        success, out = run_adb(["shell", "am", "kill-all"])
        return {
            "status": "success" if success else "error",
            "command": cmd_clean,
            "message": "Memória RAM otimizada e processos em segundo plano finalizados!" if success else f"Falha na otimização: {out}",
            "raw": out
        }

    if cmd_clean not in KEYCODES:
        return {
            "status": "error",
            "command": cmd_clean,
            "message": f"Comando '{cmd_clean}' não reconhecido."
        }

    keycode = KEYCODES[cmd_clean]
    success, out = run_adb(["shell", "input", "keyevent", str(keycode)])

    if not success and ("not found" in out.lower() or "offline" in out.lower() or "device" in out.lower()):
        connect_projector()
        success, out = run_adb(["shell", "input", "keyevent", str(keycode)])

    return {
        "status": "success" if success else "error",
        "command": cmd_clean,
        "keycode": keycode,
        "message": f"Tecla {cmd_clean.upper()} acionada com sucesso." if success else f"Erro ao enviar tecla: {out}"
    }

def launch_app(app_key_or_package: str) -> dict:
    """Inicia um aplicativo no projetor via intent / monkey."""
    key = app_key_or_package.lower().strip()
    if key in APPS:
        package = APPS[key]["package"]
        app_name = APPS[key]["name"]
    else:
        package = app_key_or_package.strip()
        app_name = package

    cmd = ["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"]
    success, out = run_adb(cmd)

    if not success and ("not found" in out.lower() or "offline" in out.lower() or "device" in out.lower()):
        connect_projector()
        success, out = run_adb(cmd)

    return {
        "status": "success" if success else "error",
        "app": app_name,
        "package": package,
        "message": f"Iniciando {app_name}..." if success else f"Falha ao iniciar {app_name}: {out}",
        "raw": out
    }

def send_text_to_projector(text: str) -> dict:
    """Envia texto completo para digitação no campo ativo do Android."""
    if not text:
        return {"status": "error", "message": "Texto vazio."}

    # Tratamento de espaços e caracteres especiais para o comando adb input text
    # No Android input text, espaço é representado por %s
    escaped = text.replace(" ", "%s")
    # Escapa caracteres que podem quebrar o shell
    escaped = re.sub(r'([\\`"\';|&<>$()])', r'\\\1', escaped)

    success, out = run_adb(["shell", "input", "text", escaped])
    return {
        "status": "success" if success else "error",
        "action": "input_text",
        "text": text,
        "message": f"Texto digitado: {text}" if success else f"Erro ao digitar: {out}"
    }

def send_key_char(char_or_code: str) -> dict:
    """Envia uma tecla individual (teclado virtual)."""
    val = str(char_or_code).strip()
    if not val:
        return {"status": "error", "message": "Caractere inválido."}

    # Teclas de controle especiais
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
        success, out = run_adb(["shell", "input", "keyevent", keycode])
        return {"status": "success" if success else "error", "key": low, "keycode": keycode}

    if val.isdigit() and len(val) > 1 and int(val) in range(1, 300):
        # Keycode direto
        success, out = run_adb(["shell", "input", "keyevent", val])
        return {"status": "success" if success else "error", "keycode": val}

    # Caractere alfanumérico ou pontuação
    if val == " ":
        success, out = run_adb(["shell", "input", "keyevent", "62"])
    else:
        escaped = val.replace(" ", "%s")
        escaped = re.sub(r'([\\`"\';|&<>$()])', r'\\\1', escaped)
        success, out = run_adb(["shell", "input", "text", escaped])

    return {"status": "success" if success else "error", "char": val}

def handle_touchpad_motion(dx: float, dy: float) -> dict:
    """Atualiza a posição virtual do cursor no projetor."""
    global cursor_state
    # Sensibilidade de movimento
    scale = 1.4
    new_x = max(0, min(1279, int(cursor_state["x"] + dx * scale)))
    new_y = max(0, min(719, int(cursor_state["y"] + dy * scale)))
    cursor_state["x"] = new_x
    cursor_state["y"] = new_y
    return {"status": "success", "cursor": cursor_state}

def handle_touchpad_tap(x: int = None, y: int = None) -> dict:
    """Executa um clique/toque na tela nas coordenadas especificadas ou no cursor atual."""
    global cursor_state
    tap_x = x if x is not None else cursor_state["x"]
    tap_y = y if y is not None else cursor_state["y"]
    success, out = run_adb(["shell", "input", "tap", str(tap_x), str(tap_y)])
    return {"status": "success" if success else "error", "x": tap_x, "y": tap_y}

def handle_touchpad_swipe(x1: int, y1: int, x2: int, y2: int, duration: int = 200) -> dict:
    """Executa um gesto de arraste (swipe) na tela."""
    success, out = run_adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
    return {"status": "success" if success else "error", "message": "Gesto executado."}

def handle_touchpad_scroll(direction: str) -> dict:
    """Executa rolagem vertical (scroll up / scroll down)."""
    if direction == "down":
        # Rola para baixo (arrasta o conteúdo para cima)
        return handle_touchpad_swipe(640, 520, 640, 200, 180)
    else:
        # Rola para cima (arrasta o conteúdo para baixo)
        return handle_touchpad_swipe(640, 200, 640, 520, 180)

# ----------------- EVENTOS WEBSOCKET (TEMPO REAL) -----------------

@socketio.on("connect")
def ws_connect():
    emit("status_update", get_projector_status())

@socketio.on("ping_status")
def ws_ping_status():
    emit("status_update", get_projector_status())

@socketio.on("set_ip")
def ws_set_ip(data):
    new_ip = data.get("ip", "").strip()
    if new_ip:
        set_projector_ip(new_ip)
        connect_projector()
    st = get_projector_status()
    socketio.emit("status_update", st)

@socketio.on("send_command")
def ws_send_command(data):
    cmd = data.get("cmd", "")
    res = execute_remote_command(cmd)
    emit("command_response", res)
    if cmd in ["home", "voltar"]:
        socketio.emit("status_update", get_projector_status())

@socketio.on("send_app")
def ws_send_app(data):
    app_key = data.get("app", "")
    res = launch_app(app_key)
    emit("command_response", res)
    time.sleep(0.8)
    socketio.emit("status_update", get_projector_status())

@socketio.on("input_text")
def ws_input_text(data):
    txt = data.get("text", "")
    res = send_text_to_projector(txt)
    emit("command_response", res)

@socketio.on("input_key")
def ws_input_key(data):
    val = data.get("key") or data.get("keycode") or data.get("char")
    res = send_key_char(val)
    emit("command_response", res)

@socketio.on("touchpad_motion")
def ws_touchpad_motion(data):
    dx = float(data.get("dx", 0))
    dy = float(data.get("dy", 0))
    res = handle_touchpad_motion(dx, dy)
    emit("cursor_update", res)

@socketio.on("touchpad_tap")
def ws_touchpad_tap(data):
    x = data.get("x")
    y = data.get("y")
    res = handle_touchpad_tap(x, y)
    emit("command_response", res)

@socketio.on("touchpad_scroll")
def ws_touchpad_scroll(data):
    direction = data.get("direction", "down")
    res = handle_touchpad_scroll(direction)
    emit("command_response", res)

@socketio.on("touchpad_click")
def ws_touchpad_click(data):
    btn = data.get("button", "left")
    if btn == "right":
        res = execute_remote_command("voltar")
    else:
        res = handle_touchpad_tap()
    emit("command_response", res)

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
