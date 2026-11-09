"""Build the two standalone Windows Tkinter installers with PyInstaller."""

import subprocess
import sys
from pathlib import Path


root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from installer.layout import APP_FILES, ICON_PATH, LOCAL_LAUNCHER


def build(role, data, admin=False):
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
               "--windowed", "--icon", str(root / ICON_PATH),
               "--paths", str(root), "--distpath", str(root / "dist"),
               "--workpath", str(root / "build" / "pyinstaller"), "--specpath", str(root / "build")]
    for source, destination in [*data, (ICON_PATH, str(ICON_PATH.parent))]:
        command.extend(["--add-data", f"{root / source}:{destination}"])
    if admin:
        command.append("--uac-admin")
    command.extend(["--name", f"install-{role}", str(root / "installer" / f"install_{role}.py")])
    subprocess.run(command, check=True)


if __name__ == "__main__":
    build("server", [(Path("launchers") / LOCAL_LAUNCHER, "launchers")], admin=True)
    build("client", [(Path("app") / name, "app") for name in APP_FILES] +
          [(Path("run.bat"), ".")])
