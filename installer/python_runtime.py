"""Discover usable CPython installations without trusting launcher registration."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.platform_paths import local_app_data_directory, program_files_directory


FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROBE = (
    "import json, struct, sys, tkinter, venv; "
    "print('COMFY_PYTHON:' + json.dumps({'executable': sys.executable, "
    "'base': getattr(sys, '_base_executable', sys.executable), 'prefix': sys.prefix, "
    "'version': list(sys.version_info[:2]), 'bits': struct.calcsize('P') * 8}))"
)


def probe_python(command):
    try:
        result = subprocess.run([*command, "-I", "-c", PROBE], capture_output=True,
                                text=True, encoding="utf-8", errors="replace",
                                creationflags=FLAGS, timeout=15)
        if result.returncode:
            return None
        marker = next(line for line in result.stdout.splitlines() if line.startswith("COMFY_PYTHON:"))
        info = json.loads(marker.partition(":")[2])
        if not isinstance(info, dict) or not isinstance(info.get("prefix"), str):
            return None
        if tuple(info["version"]) < (3, 10) or info["bits"] != 64:
            return None
        for key in ("executable", "base"):
            path = Path(info[key])
            if not path.is_absolute() or not path.is_file():
                return None
        return info
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, StopIteration):
        return None


def registry_candidates():
    if os.name != "nt":
        return
    import winreg
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, r"Software\Python\PythonCore", 0, winreg.KEY_READ | view) as core:
                    for index in range(winreg.QueryInfoKey(core)[0]):
                        version = winreg.EnumKey(core, index)
                        try:
                            with winreg.OpenKey(core, version + r"\InstallPath", 0, winreg.KEY_READ | view) as install:
                                try:
                                    yield Path(winreg.QueryValueEx(install, "ExecutablePath")[0])
                                except OSError:
                                    yield Path(winreg.QueryValueEx(install, "")[0]) / "python.exe"
                        except OSError:
                            continue
            except OSError:
                continue


def find_python_executable():
    candidates = []
    path_python = shutil.which("python.exe")
    if path_python and not any(part.casefold() == "windowsapps" for part in Path(path_python).parts):
        candidates.append(Path(path_python))
    for parent in (local_app_data_directory() / "Programs" / "Python", program_files_directory()):
        if parent.is_dir():
            candidates.extend(sorted(parent.glob("Python*/python.exe"), reverse=True))
    candidates.extend(registry_candidates())
    if not getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable))
    seen = set()
    for candidate in candidates:
        normalized = str(candidate).casefold()
        if normalized in seen or not candidate.is_file():
            continue
        seen.add(normalized)
        info = probe_python([str(candidate)])
        if info:
            base = str(Path(info["base"]).resolve())
            if Path(info["base"]).resolve() == Path(info["executable"]).resolve() or probe_python([base]):
                return base
    launcher = shutil.which("py.exe")
    if launcher:
        info = probe_python([launcher, "-3"])
        if info:
            base = str(Path(info["base"]).resolve())
            if probe_python([base]):
                return base
    return None


def venv_is_usable(directory):
    directory = Path(directory)
    executable = directory / "Scripts" / "python.exe"
    if not executable.is_file() or not (directory / "Scripts" / "pythonw.exe").is_file():
        return False
    info = probe_python([str(executable)])
    return bool(info and Path(info["executable"]).resolve() == executable.resolve()
                and Path(info["prefix"]).resolve() == directory.resolve())
