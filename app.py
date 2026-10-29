import os
import subprocess
import socket
from flask import Flask, render_template, jsonify, request
from config import (
    PROJECTOR_IP,
    PROJECTOR_PORT,
    PROJECTOR_TARGET,
    SERVER_HOST,
    SERVER_PORT,
    DEBUG_MODE,
    ADB_BIN,
    KEYCODES,
    APPS
)

app = Flask(__name__)

def run_adb(args: list[str], timeout: int = 8) -> tuple[bool, str]:
    """Executa um comando ADB diretamente no projetor de forma segura."""
    cmd = [ADB_BIN, "-s", PROJECTOR_TARGET] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        output = (res.stdout or res.stderr).strip()
        return res.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timeout de comunicação com o projetor via ADB."
    except Exception as e:
        return False, f"Erro ADB: {str(e)}"

def connect_projector() -> tuple[bool, str]:
    """Conecta ao IP do projetor via ADB se ainda não estiver conectado."""
    try:
        res = subprocess.run([ADB_BIN, "connect", PROJECTOR_TARGET], capture_output=True, text=True, timeout=8)
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
            # Extrai nome do pacote se não estiver na lista pré-definida
            if "/" in line:
                try:
                    pkg_part = line.split("/")[0].split()[-1]
                    return pkg_part
                except Exception:
                    pass
    return "Área Inicial"

def get_projector_status() -> dict:
    """Verifica a conectividade e os parâmetros de saúde do projetor."""
    success, state_out = run_adb(["get-state"], timeout=4)
    is_online = success and "device" in state_out.lower()
    
    # Se estiver offline, tenta uma reconexão transparente
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
        "ip": PROJECTOR_IP,
        "target": PROJECTOR_TARGET,
        "current_app": current_app,
        "details": state_out if is_online else "Não conectado"
    }

def execute_remote_command(cmd_name: str) -> dict:
    """Dispara eventos de tecla física do controle remoto."""
    cmd_clean = cmd_name.lower().strip()

    # Rota de otimização de RAM
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

    # Se falhou por perda momentânea de conexão, reconecta e tenta novamente
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

    # Tenta reconexão se o dispositivo tiver oscilado
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

# ----------------- ROTAS FLASK -----------------

@app.route("/")
def index():
    return render_template("index.html", projector_ip=PROJECTOR_IP, apps=APPS)

@app.route("/status")
def status_endpoint():
    return jsonify(get_projector_status())

# Rotas de Lançamento de Aplicativos
@app.route("/app/<app_name>", methods=["GET", "POST"])
@app.route("/api/app/<app_name>", methods=["GET", "POST"])
def route_launch_app(app_name):
    return jsonify(launch_app(app_name))

@app.route("/api/apps")
def route_list_apps():
    return jsonify(APPS)

# Rota Genérica para Comandos de Navegação e Teclas
@app.route("/api/cmd/<command>", methods=["GET", "POST"])
def api_command(command):
    return jsonify(execute_remote_command(command))

# Rotas Diretas para cada Ação do Controle
@app.route("/home", methods=["GET", "POST"])
def route_home():
    return jsonify(execute_remote_command("home"))

@app.route("/voltar", methods=["GET", "POST"])
def route_voltar():
    return jsonify(execute_remote_command("voltar"))

@app.route("/cima", methods=["GET", "POST"])
def route_cima():
    return jsonify(execute_remote_command("cima"))

@app.route("/baixo", methods=["GET", "POST"])
def route_baixo():
    return jsonify(execute_remote_command("baixo"))

@app.route("/esquerda", methods=["GET", "POST"])
def route_esquerda():
    return jsonify(execute_remote_command("esquerda"))

@app.route("/direita", methods=["GET", "POST"])
def route_direita():
    return jsonify(execute_remote_command("direita"))

@app.route("/ok", methods=["GET", "POST"])
def route_ok():
    return jsonify(execute_remote_command("ok"))

@app.route("/vol_up", methods=["GET", "POST"])
def route_vol_up():
    return jsonify(execute_remote_command("vol_up"))

@app.route("/vol_down", methods=["GET", "POST"])
def route_vol_down():
    return jsonify(execute_remote_command("vol_down"))

@app.route("/mute", methods=["GET", "POST"])
def route_mute():
    return jsonify(execute_remote_command("mute"))

@app.route("/power", methods=["GET", "POST"])
def route_power():
    return jsonify(execute_remote_command("power"))

@app.route("/menu", methods=["GET", "POST"])
def route_menu():
    return jsonify(execute_remote_command("menu"))

@app.route("/otimizar", methods=["GET", "POST"])
@app.route("/limpar", methods=["GET", "POST"])
def route_otimizar():
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
    print(f"[*] Conectando ao projetor em {PROJECTOR_TARGET}...")
    connected, msg = connect_projector()
    if connected:
        print(f"[+] Conectado com sucesso ao projetor em {PROJECTOR_IP}!")
    else:
        print(f"[-] Aviso na conexão ADB: {msg}")

    network_ips = get_network_ips()
    print("=" * 60)
    print("  PAINEL DE CONTROLE INTELIGENTE DO PROJETOR")
    print(f"  Status Alvo ADB : {PROJECTOR_TARGET}")
    print(f"  Acesso Local   : http://localhost:{SERVER_PORT}")
    for ip in network_ips:
        print(f"  Acesso na Rede : http://{ip}:{SERVER_PORT}")
    print("=" * 60)

    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=DEBUG_MODE)
