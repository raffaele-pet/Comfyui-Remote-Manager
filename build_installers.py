"""Build the two standalone Windows Tkinter installers with PyInstaller."""

import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parent
icon = root / "assets" / "ai-icons8.ico"
base = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--windowed", "--distpath", str(root),
        "--workpath", str(root / "build" / "pyinstaller"),
        "--specpath", str(root / "build")]

subprocess.run(base + ["--uac-admin", "--name", "install-pc-a",
                       str(root / "install_pc_a.py")], check=True)

payload = ["comfyui_remote_manager.py", "download_worker.py", "requirements.txt", "run.bat"]
args = []
for name in payload:
    args.extend(["--add-data", f"{root / name}:payload"])
args.extend(["--add-data", f"{icon}:assets"])
subprocess.run(base + args + ["--name", "install-pc-b", str(root / "install_pc_b.py")],
               check=True)
