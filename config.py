import os
import shutil

# Configurações de Rede do Projetor
PROJECTOR_IP = os.environ.get("PROJECTOR_IP", "192.168.253.112")
PROJECTOR_PORT = int(os.environ.get("PROJECTOR_PORT", 5555))
PROJECTOR_TARGET = f"{PROJECTOR_IP}:{PROJECTOR_PORT}"

# Configurações do Servidor Web Flask
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", 5050))
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")

# Auto-localização do Executável do ADB
def find_adb():
    adb_path = shutil.which("adb")
    if adb_path:
        return adb_path

    candidatos = [
        r"C:\Users\alisson.sousa\Downloads\platform-tools-latest-windows\platform-tools\adb.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        r"C:\platform-tools\adb.exe",
        os.path.expandvars(r"%USERPROFILE%\platform-tools\adb.exe"),
    ]
    for p in candidatos:
        if os.path.exists(p):
            adb_dir = os.path.dirname(p)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")
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
    }
}

