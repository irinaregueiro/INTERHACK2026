import subprocess
import sys
import os
import platform
import time

def run():
    is_windows = platform.system() == "Windows"
    
    print("🚀 Detectant sistema operatiu: " + platform.system())
    
    # Camí al python del venv
    if is_windows:
        python_bin = os.path.join("venv", "Scripts", "python.exe")
    else:
        python_bin = os.path.join("venv", "bin", "python")

    # 1. Executar ETL si existeix Datasets.xlsx
    excel_path = os.path.join("data", "raw", "Datasets.xlsx")
    if os.path.exists(excel_path):
        print("📊 S'ha detectat Datasets.xlsx. Processant dades...")
        subprocess.run([python_bin, "-m", "etl.pipeline"])
        print("✅ Dades processades.")

    print("---------------------------------------")
    
    # 2. Engegar Backend
    print("📡 Engegant el Backend (FastAPI) al port 8000...")
    backend_proc = subprocess.Popen([python_bin, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", "8000"])

    # 3. Engegar Frontend
    print("💻 Engegant el Frontend (Vite) al port 5173...")
    frontend_dir = os.path.join(os.getcwd(), "frontend")
    
    # A Windows el comando npm és npm.cmd
    npm_cmd = "npm.cmd" if is_windows else "npm"
    frontend_proc = subprocess.Popen([npm_cmd, "run", "dev"], cwd=frontend_dir)

    print("\n✅ Tot en marxa!")
    print("🔗 Dashboard: http://127.0.0.1:5173")
    print("⚠️  Prem CTRL+C per aturar-ho tot.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nAturant servidors...")
        backend_proc.terminate()
        frontend_proc.terminate()
        print("👋 Adéu!")

if __name__ == "__main__":
    run()
