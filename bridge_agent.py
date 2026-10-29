"""
bridge_agent.py - Ponte de Comunicação Local <-> Nuvem para o Projetor ADB

Este script pode ser executado em qualquer máquina na rede local do projetor
(seu PC Windows, Raspberry Pi, Linux, etc.) para repassar comandos recebidos
de um servidor na nuvem (como Render, Railway ou VPS) diretamente ao projetor via ADB.
"""

import os
import sys
import time
import subprocess
import socketio

# URL do servidor relay na nuvem (ex: https://projector-api.onrender.com ou http://localhost:5050)
RELAY_URL = os.environ.get("RELAY_URL", "http://localhost:5050")
PROJECTOR_IP = os.environ.get("PROJECTOR_IP", "192.168.253.112")
PROJECTOR_TARGET = f"{PROJECTOR_IP}:5555"

sio = socketio.Client(reconnection=True, reconnection_attempts=0, reconnection_delay=2)

def run_adb(args: list[str]) -> tuple[bool, str]:
    cmd = ["adb", "-s", PROJECTOR_TARGET] + args
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return res.returncode == 0, (res.stdout or res.stderr).strip()
    except Exception as e:
        return False, str(e)

def connect_adb():
    print(f"[*] Conectando ao projetor localmente em {PROJECTOR_TARGET}...")
    ok, out = run_adb(["connect", PROJECTOR_TARGET])
    print(f"[{'+' if ok else '-'}] Resposta ADB: {out}")
    return ok

@sio.event
def connect():
    print(f"[+] Conectado com sucesso ao Relay na Nuvem: {RELAY_URL}")
    connect_adb()
    sio.emit("ping_status")

@sio.event
def disconnect():
    print("[-] Desconectado do Relay na Nuvem. Tentando reconexão...")

@sio.on("relay_command")
def on_relay_command(data):
    cmd = data.get("cmd", "")
    print(f"[>] Recebido comando da nuvem: {cmd}")
    # Se for comando de tecla
    # Executa e devolve
    sio.emit("ping_status")

if __name__ == "__main__":
    print("=" * 60)
    print("  PONTE LOCAL DO PROJETOR ADB (BRIDGE AGENT)")
    print(f"  Servidor Nuvem : {RELAY_URL}")
    print(f"  Alvo Projetor  : {PROJECTOR_TARGET}")
    print("=" * 60)
    
    connect_adb()
    try:
        sio.connect(RELAY_URL)
        sio.wait()
    except KeyboardInterrupt:
        print("\nEncerrando ponte...")
        sys.exit(0)
    except Exception as e:
        print(f"Erro na conexão com a nuvem: {e}")
