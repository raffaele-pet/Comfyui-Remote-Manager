"""Graphical setup wizard for the Windows PC controlling ComfyUI."""

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from installer_common import (FLAGS, InstallerWindow, create_shortcut, desktop_directory, find_tailscale,
                              open_tailscale, resource_path, run_command, tailscale_ip,
                              validate_config, winget_install, write_json)


class PcBInstaller(InstallerWindow):
    def __init__(self):
        super().__init__("Installa PC B · ComfyUI Remote Manager")
        self.install_dir = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "ComfyUIRemoteManager"
        self.app_dir = self.install_dir / "app"
        self.venv_dir = self.install_dir / ".venv"
        self.intro_step()

    def intro_step(self):
        self.page("1 / 3 · Installa su PC B",
                  "L'installer prepara Tailscale, Python, ComfyUI Remote Manager e un collegamento sul Desktop. Vedrai qui sotto l'avanzamento.")
        self.label("Cartella di installazione: " + str(self.install_dir))
        self.label("I file del programma sono inclusi nell'installer.")
        self.button("Avvia installazione", self.start_install, primary=True)

    def start_install(self):
        self.run_async(self.install_components, lambda _result: self.tailscale_step())

    def find_python(self):
        launcher = shutil.which("py.exe")
        executable = shutil.which("python.exe")
        if executable and "WindowsApps" in executable:
            executable = None
        candidates = [Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Python" / "Python313" / "python.exe",
                      Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Python313" / "python.exe"]
        executable = executable or next((str(path) for path in candidates if path.is_file()), None)
        return launcher, executable

    def install_components(self):
        if not find_tailscale():
            winget_install("Tailscale.Tailscale", self.log)
        if not find_tailscale():
            raise RuntimeError("Tailscale installato, ma l'eseguibile non è stato trovato. Riavvia l'installer.")
        self.log("Tailscale pronto.")

        launcher, python = self.find_python()
        if not launcher and not python:
            winget_install("Python.Python.3.13", self.log)
            launcher, python = self.find_python()
        if not launcher and not python:
            raise RuntimeError("Python installato, ma non trovato. Riavvia l'installer.")

        payload = resource_path("payload")
        if not payload.is_dir():
            payload = Path(__file__).parent
        self.app_dir.mkdir(parents=True, exist_ok=True)
        for name in ("comfyui_remote_manager.py", "download_worker.py", "requirements.txt", "run.bat"):
            source = payload / name
            if not source.is_file():
                raise RuntimeError("File incluso nell'installer non trovato: " + name)
            if source.resolve() != (self.app_dir / name).resolve():
                shutil.copy2(source, self.app_dir / name)
        icon_source = resource_path("assets") / "ai-icons8.ico"
        if not icon_source.is_file():
            raise RuntimeError("Icona Icons8 non inclusa nell'installer.")
        icon_target = self.app_dir / "ai-icons8.ico"
        if icon_source.resolve() != icon_target.resolve():
            shutil.copy2(icon_source, icon_target)
        self.log("File dell'app installati.")

        venv_python = self.venv_dir / "Scripts" / "python.exe"
        if not venv_python.is_file():
            command = [launcher, "-3", "-m", "venv", str(self.venv_dir)] if launcher else \
                      [python, "-m", "venv", str(self.venv_dir)]
            run_command(command, self.log)
        self.log("Installazione delle dipendenze Python...")
        run_command([str(venv_python), "-m", "pip", "install", "-r",
                     str(self.app_dir / "requirements.txt")], self.log)

        desktop = desktop_directory()
        create_shortcut(desktop / "ComfyUI Remote Manager.lnk",
                        self.app_dir / "run.bat", self.app_dir, icon_target)
        self.log("Collegamento a run.bat creato sul Desktop con l'icona richiesta.")

    def tailscale_step(self):
        self.page("2 / 3 · Accesso a Tailscale",
                  "Apri Tailscale e accedi con la stessa tailnet usata su PC A. Torna qui e verifica la connessione prima di configurare l'app.")
        self.button("Apri Tailscale", self.launch_tailscale)
        self.button("Verifica accesso", self.verify_tailscale, primary=True)

    def launch_tailscale(self):
        try:
            open_tailscale()
            self.log("Tailscale aperto. Completa l'accesso nel browser.")
        except Exception as error:
            messagebox.showerror("Tailscale", str(error), parent=self.root)

    def verify_tailscale(self):
        self.run_async(self.check_tailscale, lambda _ip: self.choice_step())

    def check_tailscale(self):
        ip = tailscale_ip()
        if not ip:
            raise RuntimeError("Nessun IP Tailscale rilevato. Completa l'accesso e riprova.")
        self.log("Accesso Tailscale verificato: " + ip)
        return ip

    def choice_step(self):
        self.page("3 / 3 · Configura PC A",
                  "Scegli come inserire i dati di PC A. Puoi importarli, scriverli qui, oppure aprire il programma e compilarli nella sua interfaccia.")
        self.label("La password SSH verrà richiesta dal programma e non è nel file esportato da PC A.")
        self.button("Importa configurazione", self.import_config, primary=True)
        self.button("Inserisci a mano", self.manual_step)
        self.button("Apri il programma", self.open_app)

    def profile_path(self):
        return Path(os.environ["LOCALAPPDATA"]) / "ComfyUIRemoteManager" / "connection.json"

    def save_profile(self, config):
        config = validate_config(config)
        profile = {key: config[key] for key in ("host", "port", "user", "comfy_dir",
                                                 "start_batch", "cloudflared_exe")}
        profile.update({"remember_password": False, "password": ""})
        write_json(self.profile_path(), profile)
        self.log("Profilo PC A salvato su questo PC.")
        self.ready_step()

    def import_config(self):
        path = filedialog.askopenfilename(parent=self.root, title="Configurazione di PC A",
                                          filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            self.save_profile(config)
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Configurazione", str(error), parent=self.root)

    def manual_step(self):
        self.page("3 / 3 · Inserimento manuale",
                  "Inserisci i dati di PC A. Li trovi nella finestra dell'installer PC A o nelle impostazioni di Windows e Tailscale.")
        self.host_var = self.entry("Host o IP Tailscale di PC A")
        self.user_var = self.entry("Utente Windows di PC A")
        self.port_var = self.entry("Porta SSH", "22")
        self.comfy_var = self.entry("Cartella ComfyUI Portable su PC A (es. C:\\ComfyUI)")
        self.batch_var = self.entry("Batch di avvio", "run_nvidia_gpu.bat")
        self.cloudflare_var = self.entry("Percorso cloudflared su PC A",
                                        r"C:\ProgramData\ComfyUIRemoteManager\cloudflared.exe")
        self.button("Salva e continua", self.save_manual, primary=True)
        self.button("Indietro", self.choice_step)

    def save_manual(self):
        try:
            self.save_profile({"version": 1, "host": self.host_var.get(),
                               "port": self.port_var.get(), "user": self.user_var.get(),
                               "comfy_dir": self.comfy_var.get(),
                               "start_batch": self.batch_var.get(),
                               "cloudflared_exe": self.cloudflare_var.get()})
        except (ValueError, TypeError) as error:
            messagebox.showerror("Configurazione", str(error), parent=self.root)

    def ready_step(self):
        self.page("Installazione completata",
                  "ComfyUI Remote Manager è pronto. Aprilo, inserisci la password SSH di PC A e premi Connetti.")
        self.label("Trovi il collegamento a run.bat sul Desktop con l'icona richiesta.")
        self.button("Apri ComfyUI Remote Manager", self.open_app, primary=True)
        self.button("Chiudi", self.root.destroy)

    def open_app(self):
        subprocess.Popen([str(self.venv_dir / "Scripts" / "pythonw.exe"),
                          str(self.app_dir / "comfyui_remote_manager.py")],
                         cwd=self.app_dir, creationflags=FLAGS)
        self.log("ComfyUI Remote Manager aperto.")


if __name__ == "__main__":
    installer = PcBInstaller()
    if "--self-test" in sys.argv:
        installer.root.withdraw()
        assert (resource_path("payload") / "comfyui_remote_manager.py").is_file()
        assert (resource_path("assets") / "ai-icons8.ico").is_file()
        installer.root.destroy()
    else:
        installer.root.mainloop()
