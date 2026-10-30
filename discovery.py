"""
Auto-descoberta e manutenção da conexão ADB com o projetor (zero configuração de IP).

Somente rede local. Ordem de tentativa a cada ciclo sem conexão:
  1. Dicas recentes (último IP conectado / IP enviado pelo painel)
  2. IP associado ao MAC do HY320 na tabela ARP
  3. Varredura da sub-rede local procurando a porta ADB aberta
Endereços fora da rede local (IPs públicos, Tailscale 100.x) são ignorados.
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
    PROJECTOR_MAC,
    LAN_SUBNET,
    is_lan_ip,
    get_projector_target,
    set_projector_ip,
)

CHECK_INTERVAL = 4       # segundos entre verificações
FULL_SCAN_INTERVAL = 30  # varredura completa da LAN no máximo a cada 30s

state = {
    "online": False,
    "target": None,
    "via": None,           # "lan"
    "scanning": False,
    "last_change": None,
}

_hints = [get_projector_target()]
_lock = threading.Lock()
_started = False
_on_change = None


def _adb(args, timeout=6):
    try:
        res = subprocess.run([ADB_BIN] + list(args), capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, (res.stdout or res.stderr).strip()
    except Exception as e:
        return False, str(e)


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
    ip, port = target.rsplit(":", 1)
    if not is_lan_ip(ip):
        return False
    if is_device(target):
        return True
    if not _port_open(ip, int(port)):
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


def _set_state(online, target=None, via=None):
    changed = online != state["online"] or target != state["target"]
    state.update(online=online, target=target, via=via)
    if changed:
        state["last_change"] = time.time()
        if online:
            set_projector_ip(target.split(":")[0])
            print(f"[+] Projetor conectado via {via}: {target}")
        else:
            print("[-] Projetor desconectado. Procurando...")
        if _on_change:
            try:
                _on_change()
            except Exception as e:
                print(f"[-] Erro ao notificar mudança de status: {e}")


def _via(target):
    return "lan"


def discover_once(full_scan=False):
    """Uma rodada de descoberta. Retorna o alvo conectado ou None."""
    with _lock:
        candidates = list(_hints)
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
