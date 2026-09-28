"""Arranca backend y frontend en ventanas separadas, espera a que respondan y abre el
navegador a pantalla completa."""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = ROOT / ".venv"
PYTHON = VENV / "Scripts" / "python.exe"
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
NEXT_BIN = FRONTEND / "node_modules" / "next" / "dist" / "bin" / "next"

BACKEND_PORT = 8000
FRONTEND_PORT = 3000
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

TIMEOUT_SEGUNDOS = 240
INTERVALO_SEGUNDOS = 2

NAVEGADORES = (
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
)


class ArranqueError(Exception):
    pass


def puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def esperar(url: str, nombre: str, limite: float) -> None:
    transcurrido = 0.0
    while transcurrido < limite:
        try:
            with urllib.request.urlopen(url, timeout=5) as respuesta:
                if respuesta.status < 500:
                    print(f"  {nombre} listo en {url}")
                    return
        except (urllib.error.URLError, OSError, ValueError):
            pass
        time.sleep(INTERVALO_SEGUNDOS)
        transcurrido += INTERVALO_SEGUNDOS
    raise ArranqueError(f"{nombre} no respondio en {limite:.0f} s: {url}")


def consola(nueva: bool) -> int:
    return subprocess.CREATE_NEW_CONSOLE if nueva else 0


def lanzar(comando: list[str], cwd: Path, entorno: dict[str, str] | None = None) -> None:
    subprocess.Popen(
        comando,
        cwd=str(cwd),
        env=entorno,
        creationflags=consola(True),
    )


def arrancar_backend() -> None:
    entorno = dict(os.environ)
    entorno["PYTHONPATH"] = str(BACKEND / "src")
    entorno["PYTHONUNBUFFERED"] = "1"
    lanzar(
        [
            str(PYTHON),
            "-m",
            "uvicorn",
            "main:app",
            "--app-dir",
            "src",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=BACKEND,
        entorno=entorno,
    )


def arrancar_frontend() -> None:
    entorno = dict(os.environ)
    entorno["BACKEND_URL"] = os.environ.get("BACKEND_URL", BACKEND_URL)
    entorno["NEXT_TELEMETRY_DISABLED"] = "1"
    entorno["NODE_ENV"] = "development"
    lanzar(
        ["node", str(NEXT_BIN), "dev", "-p", str(FRONTEND_PORT), "-H", "127.0.0.1"],
        cwd=FRONTEND,
        entorno=entorno,
    )


def abrir_navegador(url: str) -> str:
    for ruta in NAVEGADORES:
        if ruta.is_file():
            subprocess.Popen([str(ruta), "--new-window", "--start-fullscreen", url])
            return ruta.name
    os.startfile(url)
    return "navegador del sistema (sin pantalla completa)"


def comprobar_requisitos() -> None:
    if not PYTHON.is_file():
        raise ArranqueError(f"No existe el entorno virtual: {VENV}")
    if not NEXT_BIN.is_file():
        raise ArranqueError(f"Faltan las dependencias del frontend. Ejecuta en {FRONTEND}: npm install")
    for puerto, nombre in ((BACKEND_PORT, "backend"), (FRONTEND_PORT, "frontend")):
        if puerto_ocupado(puerto):
            raise ArranqueError(f"El puerto {puerto} ({nombre}) ya esta ocupado. Cierra el proceso que lo usa.")


def main() -> int:
    print("ContabilidadV1 - arranque en modo desarrollo\n")
    try:
        comprobar_requisitos()
    except ArranqueError as error:
        print(f"ERROR: {error}")
        return 1

    print("Levantando backend (uvicorn, puerto 8000)...")
    arrancar_backend()
    print("Levantando frontend (next dev, puerto 3000)...")
    arrancar_frontend()

    try:
        esperar(f"{BACKEND_URL}/health", "backend", TIMEOUT_SEGUNDOS)
        esperar(f"{FRONTEND_URL}/login", "frontend", TIMEOUT_SEGUNDOS)
    except ArranqueError as error:
        print(f"\nERROR: {error}")
        print("Revisa las ventanas del backend y del frontend para ver el detalle.")
        return 1

    navegador = abrir_navegador(FRONTEND_URL)
    print(f"\nTodo listo. Abriendo {FRONTEND_URL} a pantalla completa con {navegador}.")
    print(f"API: {BACKEND_URL}/api/v1  |  Health: {BACKEND_URL}/health")
    print("Cierra las dos ventanas de consola para detener los servidores.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
