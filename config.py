import os
import shutil

# Configurações de Rede do Projetor (Dinâmico: Suporta IP Local, Tailscale 100.x ou Nuvem)
DEFAULT_PROJECTOR_IP = os.environ.get("PROJECTOR_IP", "192.168.253.112")
PROJECTOR_PORT = int(os.environ.get("PROJECTOR_PORT", 5555))

# Estado mutável do IP em tempo de execução
_current_ip = DEFAULT_PROJECTOR_IP

def get_projector_ip() -> str:
    global _current_ip
    return _current_ip

def set_projector_ip(new_ip: str) -> str:
    global _current_ip
    cleaned = new_ip.strip()
    if ":" in cleaned:
        # Se o usuário digitou ip:porta
        cleaned = cleaned.split(":")[0]
    _current_ip = cleaned
    return _current_ip

def get_projector_target() -> str:
    return f"{get_projector_ip()}:{PROJECTOR_PORT}"

# Configurações do Servidor Web Flask e WebSocket
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", 5050))
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

# Auto-localização do Executável do ADB (Multiplataforma: Windows e Linux/Container)
def find_adb():
    adb_path = shutil.which("adb")
    if adb_path:
        return adb_path

    candidatos_windows = [
        r"C:\Users\alisson.sousa\Downloads\platform-tools-latest-windows\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\platform-tools\adb.exe",
        os.path.expandvars(r"%USERPROFILE%\platform-tools\adb.exe"),
    ]
    for p in candidatos_windows:
        if os.path.exists(p):
            adb_dir = os.path.dirname(p)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
            return p

    candidatos_linux = [
        "/usr/bin/adb",
        "/usr/local/bin/adb",
        "/opt/android-sdk/platform-tools/adb"
    ]
    for p in candidatos_linux:
        if os.path.exists(p):
            return p

    return "adb"

ADB_BIN = find_adb()

# Mapeamento de Teclas Físicas Android (Keycodes)
KEYCODES = {
    "home": 3,         # KEYCODE_HOME
    "voltar": 4,       # KEYCODE_BACK
    "cima": 19,        # KEYCODE_DPAD_UP
    "baixo": 20,       # KEYCODE_DPAD_DOWN
    "esquerda": 21,    # KEYCODE_DPAD_LEFT
    "direita": 22,     # KEYCODE_DPAD_RIGHT
    "ok": 23,          # KEYCODE_DPAD_CENTER
    "vol_up": 24,      # KEYCODE_VOLUME_UP
    "vol_down": 25,    # KEYCODE_VOLUME_DOWN
    "power": 26,       # KEYCODE_POWER
    "mute": 164,       # KEYCODE_VOLUME_MUTE
    "menu": 82         # KEYCODE_MENU
}

# Aplicativos Principais do Projetor
APPS = {
    "youtube": {
        "name": "YouTube",
        "package": "com.google.android.youtube.tv",
        "icon": "youtube",
        "color": "#ef4444"
    },
    "netflix": {
        "name": "Netflix",
        "package": "com.netflix.mediaclient",
        "icon": "netflix",
        "color": "#e11d48"
    },
    "prime": {
        "name": "Prime Video",
        "package": "com.amazon.amazonvideo.livingroom",
        "icon": "prime",
        "color": "#0284c7"
    },
    "youcine": {
        "name": "YouCine",
        "package": "com.world.youcinetv",
        "icon": "movie",
        "color": "#f59e0b"
    },
    "chrome": {
        "name": "Chrome",
        "package": "com.android.chrome",
        "icon": "chrome",
        "color": "#3b82f6"
    },
    "unitv": {
        "name": "UniTV",
        "package": "com.unitvnet.tvod",
        "icon": "tv",
        "color": "#8b5cf6"
    },
    "settings": {
        "name": "Configurações",
        "package": "com.htc.htcsettings",
        "icon": "settings",
        "color": "#64748b"
    },
    "launcher": {
        "name": "Início",
        "package": "com.htc.htclauncherhighenglishd08",
        "icon": "home",
        "color": "#0ea5e9"
    },
    "tailscale": {
        "name": "Tailscale",
        "package": "com.tailscale.ipn",
        "icon": "shield",
        "color": "#4f46e5"
    }
}
