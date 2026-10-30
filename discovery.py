"""
Auto-descoberta e manutenção da conexão ADB com o projetor (zero configuração de IP).

Ordem de tentativa a cada ciclo sem conexão:
  1. IP do Tailscale do projetor (100.x)
  2. Dicas recentes (último IP conectado / IP enviado pelo painel)
  3. IP associado ao MAC do HY320 na tabela ARP
  4. Varredura da sub-rede local procurando a porta ADB aberta
Ao conectar, blinda o Tailscale no projetor contra o gerenciador de memória do Android.
"""
import ipaddress
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from config import (
    ADB_BIN,
    PROJECTOR_PORT,
    PROJECTOR_TAILSCALE_IP,
    PROJECTOR_MAC,
    LAN_SUBNET,
    TAILSCALE_PACKAGE,
    TAILSCALE_USERSPACE,
    get_projector_target,
    set_projector_ip,
)

CHECK_INTERVAL = 4       # segundos entre verificações
FULL_SCAN_INTERVAL = 30  # varredura completa da LAN no máximo a cada 30s

state = {
    "online": False,
    "target": None,
    "via": None,           # "tailscale" | "lan"
    "scanning": False,
    "last_change": None,
    "tailscale_hardened": False,
}

_hints = [get_projector_target()]
_lock = threading.Lock()
_started = False
_on_change = None


_forwards = {}  # alvo lógico (100.x:5555) -> (porta local, processo socat)
_FORWARD_BASE_PORT = 15000


def _is_tailnet(ip):
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        return False


def serial(target):
    """
    Endereço que o ADB deve usar para o alvo lógico.
    No modo userspace (nuvem) não existe rota do SO para 100.x, então cada alvo do tailnet
    ganha um socat local que encaminha via 'tailscale nc'; fora disso o alvo é usado como está.
    """
    if not TAILSCALE_USERSPACE or not target:
        return target
    ip, port = target.rsplit(":", 1)
    if not _is_tailnet(ip):
        return target
    with _lock:
        fwd = _forwards.get(target)
        if fwd and fwd[1].poll() is None:
            return f"127.0.0.1:{fwd[0]}"
        local_port = fwd[0] if fwd else _FORWARD_BASE_PORT + len(_forwards)
        proc = subprocess.Popen(
            ["socat", f"TCP-LISTEN:{local_port},bind=127.0.0.1,reuseaddr,fork",
             f"EXEC:tailscale nc {ip} {port}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        _forwards[target] = (local_port, proc)
    time.sleep(0.3)  # socat precisa abrir o listen antes do adb connect
    return f"127.0.0.1:{local_port}"


def _adb(args, timeout=6):
    # Traduz o alvo lógico de '-s X' e 'connect/disconnect X' para o endereço real do ADB
    args = list(args)
    for i, a in enumerate(args[:-1]):
        if a in ("-s", "connect", "disconnect"):
            args[i + 1] = serial(args[i + 1])
    try:
        res = subprocess.run([ADB_BIN] + args, capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, (res.stdout or res.stderr).strip()
    except Exception as e:
        return False, str(e)


def _reachable(ip, port):
    """Na nuvem pinga pelo Tailscale (sem rota do SO); localmente testa a porta TCP."""
    if TAILSCALE_USERSPACE and _is_tailnet(ip):
        try:
            res = subprocess.run(["tailscale", "ping", "--c", "1", "--until-direct=false", "--timeout", "5s", ip],
                                 capture_output=True, text=True, timeout=8)
            return res.returncode == 0
        except Exception:
            return False
    return _port_open(ip, port)


def _port_open(ip, port=PROJECTOR_PORT, timeout=1.5):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def _with_port(ip_or_target):
    return ip_or_target if ":" in ip_or_target else f"{ip_or_target}:{PROJECTOR_PORT}"


def is_device(target):
    ok, out = _adb(["-s", target, "get-state"], timeout=4)
    return ok and out.strip() == "device"


def try_connect(target):
    """Conecta ao alvo se a porta estiver aberta; descarta entradas 'offline' presas no servidor ADB."""
    if is_device(target):
        return True
    ip, port = target.rsplit(":", 1)
    if not _reachable(ip, int(port)):
        return False
    _adb(["disconnect", target], timeout=4)
    _, out = _adb(["connect", target], timeout=10)
    return "connected to" in out.lower() and is_device(target)


def _ip_from_arp(mac):
    """Procura na tabela ARP/neighbors o IP do MAC informado (Windows usa '-', Linux usa ':')."""
    if not mac:
        return None
    wanted = mac.lower().replace("-", ":")
    for cmd in (["arp", "-a"], ["ip", "neigh"]):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=4).stdout
        except Exception:
            continue
        for line in out.splitlines():
            m_ip = re.search(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b", line)
            m_mac = re.search(r"([0-9a-fA-F]{2}(?:[-:][0-9a-fA-F]{2}){5})", line)
            if m_ip and m_mac and m_mac.group(1).lower().replace("-", ":") == wanted:
                return m_ip.group(1)
    return None


def _scan_lan():
    """Varre a sub-rede em paralelo e retorna os IPs com a porta ADB aberta."""
    if not LAN_SUBNET:
        return []
    hosts =[str(h) for h in ipaddress.ip_network(LAN_SUBNET, strict=False).hosts()]
    with ThreadPoolExecutor(max_workers=64) as pool:
        found = pool.map(lambda ip: ip if _port_open(ip, timeout=0.6) else None, hosts)
    return [ip for ip in found if ip]


def harden_tailscale(target):
    """Impede que o Android mate o Tailscale em segundo plano e religa a VPN."""
    ok, out = _adb(["-s", target, "shell", "pm", "list", "packages", TAILSCALE_PACKAGE])
    if TAILSCALE_PACKAGE not in out:
        return {"installed": False}
    cmds = [
        ["dumpsys", "deviceidle", "whitelist", f"+{TAILSCALE_PACKAGE}"],
        ["cmd", "appops", "set", TAILSCALE_PACKAGE, "RUN_IN_BACKGROUND", "allow"],
        ["cmd", "appops", "set", TAILSCALE_PACKAGE, "RUN_ANY_IN_BACKGROUND", "allow"],
        ["am", "set-standby-bucket", TAILSCALE_PACKAGE, "active"],
        # VPN sempre ativa (equivalente ao toggle "Always-on VPN"; sem lockdown para não cortar a rede)
        ["settings", "put", "secure", "always_on_vpn_app", TAILSCALE_PACKAGE],
        ["settings", "put", "secure", "always_on_vpn_lockdown", "0"],
        # Religa a VPN sem abrir a interface do app na tela
        ["am", "broadcast", "-a", "com.tailscale.ipn.CONNECT_VPN", "-n", f"{TAILSCALE_PACKAGE}/.IPNReceiver"],
    ]
    results = {}
    for c in cmds:
        ok, out = _adb(["-s", target, "shell"] + c)
        results[" ".join(c)] = ok and "error" not in out.lower() and "exception" not in out.lower()

    # O broadcast nem sempre sobe a VPN: se não há interface 100.x, abre o app e volta à tela inicial
    time.sleep(3)
    _, addrs = _adb(["-s", target, "shell", "ip", "-o", "-4", "addr"])
    if "inet 100." not in addrs:
        _adb(["-s", target, "shell", "monkey", "-p", TAILSCALE_PACKAGE, "-c", "android.intent.category.LEANBACK_LAUNCHER", "1"])
        time.sleep(8)
        _adb(["-s", target, "shell", "input", "keyevent", "3"])
        _, addrs = _adb(["-s", target, "shell", "ip", "-o", "-4", "addr"])
    results["vpn_up"] = "inet 100." in addrs
    return {"installed": True, "results": results}


def _set_state(online, target=None, via=None):
    changed = online != state["online"] or target != state["target"]
    state.update(online=online, target=target, via=via)
    if changed:
        state["last_change"] = time.time()
        if online:
            set_projector_ip(target.split(":")[0])
            hardened = harden_tailscale(target)
            state["tailscale_hardened"] = hardened.get("installed", False) and all(hardened.get("results", {}).values())
            print(f"[+] Projetor conectado via {via}: {target} | Tailscale blindado: {state['tailscale_hardened']}")
        else:
            print("[-] Projetor desconectado. Procurando...")
        if _on_change:
            try:
                _on_change()
            except Exception as e:
                print(f"[-] Erro ao notificar mudança de status: {e}")


def _via(target):
    return "tailscale" if target.startswith("100.") else "lan"


def discover_once(full_scan=False):
    """Uma rodada de descoberta. Retorna o alvo conectado ou None."""
    candidates = [_with_port(PROJECTOR_TAILSCALE_IP)]
    with _lock:
        candidates += [h for h in _hints if h not in candidates]
    arp_ip = _ip_from_arp(PROJECTOR_MAC)
    if arp_ip:
        candidates.append(_with_port(arp_ip))

    for target in dict.fromkeys(candidates):
        if try_connect(target):
            return target

    if full_scan:
        state["scanning"] = True
        try:
            for ip in _scan_lan():
                target = _with_port(ip)
                if target not in candidates and try_connect(target):
                    return target
        finally:
            state["scanning"] = False
    return None


def add_hint(target):
    """Registra um IP sugerido (painel/usuário) para ser testado logo no próximo ciclo."""
    target = _with_port(target)
    with _lock:
        if target in _hints:
            _hints.remove(target)
        _hints.insert(0, target)
        del _hints[5:]


def prefer(target):
    """Troca explícita de alvo (usuário digitou um IP): conecta agora e passa a usar esse alvo."""
    target = _with_port(target)
    add_hint(target)
    if try_connect(target):
        _set_state(True, target, _via(target))
        return True
    return False


def _loop():
    last_full_scan = 0
    while True:
        try:
            current = state["target"]
            if state["online"] and current and is_device(current):
                time.sleep(CHECK_INTERVAL)
                continue
            if state["online"]:
                _set_state(False)
            now = time.time()
            full = now - last_full_scan >= FULL_SCAN_INTERVAL
            if full:
                last_full_scan = now
            found = discover_once(full_scan=full)
            if found:
                add_hint(found)
                _set_state(True, found, _via(found))
                continue
        except Exception as e:
            print(f"[-] Erro na auto-descoberta: {e}")
        time.sleep(CHECK_INTERVAL)


def start(on_change=None):
    """Inicia a thread de auto-descoberta (idempotente)."""
    global _started, _on_change
    _on_change = on_change
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="projector-discovery", daemon=True).start()
