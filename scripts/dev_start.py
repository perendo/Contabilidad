"""Arrancador multiplataforma de desarrollo para ContabilidadV1.

Comprueba puertos, dependencias, arranca backend y frontend en paralelo,
espera a que respondan y abre el navegador por defecto.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def check_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def find_python() -> str:
    # Soporta Windows y POSIX
    if sys.platform == "win32":
        venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT / ".venv" / "bin" / "python"
    
    if venv_py.exists():
        return str(venv_py)
    return sys.executable

def start_backend() -> subprocess.Popen:
    py = find_python()
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cwd = ROOT / "backend"
    cmd = [py, "-m", "uvicorn", "main:app", "--reload", "--port", "8000", "--host", "127.0.0.1"]
    
    print(f"-> Arrancando backend en http://127.0.0.1:8000 ...")
    if sys.platform == "win32":
        return subprocess.Popen(cmd, cwd=str(cwd), env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return subprocess.Popen(cmd, cwd=str(cwd), env=env)

def start_frontend() -> subprocess.Popen:
    cwd = ROOT / "frontend"
    cmd = ["npm", "run", "dev"]
    print(f"-> Arrancando frontend en http://localhost:3000 ...")
    if sys.platform == "win32":
        return subprocess.Popen(cmd, cwd=str(cwd), shell=True, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    return subprocess.Popen(cmd, cwd=str(cwd))

def wait_for_url(port: int, timeout: int = 30) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if check_port(port):
            return True
        time.sleep(0.5)
    return False

def main():
    print("=== Arrancador de Desarrollo ContabilidadV1 ===")
    
    if check_port(8000):
        print("AVISO: El puerto 8000 (backend) ya está ocupado.")
    if check_port(3000):
        print("AVISO: El puerto 3000 (frontend) ya está ocupado.")
        
    p_backend = start_backend()
    p_frontend = start_frontend()
    
    print("Esperando a que los servicios estén listos...")
    backend_ok = wait_for_url(8000)
    frontend_ok = wait_for_url(3000)
    
    if backend_ok and frontend_ok:
        print("\n¡Servicios levantados con éxito!")
        print("Frontend: http://localhost:3000")
        print("Backend Docs: http://127.0.0.1:8000/docs")
        time.sleep(1)
        webbrowser.open("http://localhost:3000")
    else:
        print("\nAtención: Algunos servicios tardaron en responder.")
    
    print("\nPresiona Ctrl+C para detener ambos servicios.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo servicios...")
        p_backend.terminate()
        p_frontend.terminate()
        print("Servicios detenidos.")

if __name__ == "__main__":
    main()
