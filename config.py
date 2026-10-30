import ipaddress
import os
import shutil

# Configurações de Rede do Projetor (somente rede local)
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

# Auto-descoberta do projetor HY320 na rede local (ordem: último IP -> MAC na ARP -> varredura da LAN)
PROJECTOR_MAC = os.environ.get("PROJECTOR_MAC", "26:80:ab:03:43:dd")
LAN_SUBNET = os.environ.get("LAN_SUBNET", "192.168.253.0/24")  # vazio desativa a varredura

# Acesso permitido somente da mesma rede: loopback e faixas privadas (RFC 1918 / link-local / IPv6 ULA).
# A faixa do Tailscale (100.64.0.0/10) e IPs públicos ficam de fora de propósito.
_LAN_NETWORKS = [ipaddress.ip_network(n) for n in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16",
    "::1/128", "fc00::/7", "fe80::/10",
)]

def is_lan_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(str(ip).split("%")[0])
    except ValueError:
        return False
    if getattr(addr, "ipv4_mapped", None):
        addr = addr.ipv4_mapped
    return any(addr in net for net in _LAN_NETWORKS)

# Configurações do Servidor Web Flask e WebSocket
SERVER_HOST = os.environ.get("HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("PORT", 5050))
DEBUG_MODE = os.environ.get("FLASK_DEBUG", "0").lower() in ("1", "true")

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
    "smarttube": {
        "name": "SmartTube (YouTube Leve)",
        "package": "org.smarttube.stable",
        "icon": "youtube",
        "color": "#ef4444"
    },
    "youtube": {
        "name": "SmartTube (YouTube Leve)",
        "package": "org.smarttube.stable",
        "icon": "youtube",
        "color": "#ef4444"
    },
    "youtube_original": {
        "name": "YouTube Oficial",
        "package": "com.google.android.youtube.tv",
        "icon": "youtube",
        "color": "#dc2626"
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
    "projectivy": {
        "name": "Projectivy Launcher",
        "package": "com.spocky.projengmenu",
        "icon": "home",
        "color": "#10b981"
    }
}
