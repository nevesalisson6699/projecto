import subprocess
import sys

IP_PROJETOR = "192.168.253.112"

def executar_adb(comando: list[str]) -> str:
    """Executa um comando ADB direcionado ao IP do projetor."""
    resultado = subprocess.run(
        ["adb", "-s", IP_PROJETOR, *comando],
        capture_output=True,
        text=True,
        check=True,
    )
    return resultado.stdout

def conectar():
    print(f"Conectando ao projetor em {IP_PROJETOR}...")
    resultado = subprocess.run(
        ["adb", "connect", IP_PROJETOR],
        capture_output=True,
        text=True,
        check=True,
    )
    print(resultado.stdout or resultado.stderr)

def analisar_memoria():
    print("\n🔍 [1/2] Analisando processos que consomem mais memória (TOP)...")
    top_output = executar_adb(["shell", "top", "-n", "1", "-b", "-m", "10"])
    print(top_output)

    print("\n📊 [2/2] Resumo Geral de Memória (RAM):")
    mem_output = executar_adb(["shell", "dumpsys", "meminfo"])
    # Filtra as linhas mais importantes do meminfo para não poluir o terminal
    linhas = [linha for linha in mem_output.split('\n') if "TOTAL" in linha or "Free RAM" in linha or "Used RAM" in linha]
    print("\n".join(linhas[:15]))

def limpar_processos_inativos():
    print("\n🧹 Listando apps de terceiros instalados para otimização...")
    res = executar_adb(["shell", "pm", "list", "packages", "-3"])
    print("Apps de terceiros encontrados:\n", res)

if __name__ == "__main__":
    try:
        conectar()
        if len(sys.argv) > 1:
            acao = sys.argv[1]
            if acao == "analisar":
                analisar_memoria()
            elif acao == "limpar":
                limpar_processos_inativos()
            else:
                print("Comando desconhecido. Use: python projetor_autonomo.py [analisar|limpar]")
                sys.exit(2)
        else:
            analisar_memoria()
    except FileNotFoundError:
        print("Erro: ADB não encontrado. Instale o Android Platform Tools e configure o PATH.")
        sys.exit(1)
    except subprocess.CalledProcessError as erro:
        detalhe = erro.stderr or erro.stdout or str(erro)
        print(f"Erro ao executar comando ADB: {detalhe.strip()}")
        sys.exit(erro.returncode or 1)