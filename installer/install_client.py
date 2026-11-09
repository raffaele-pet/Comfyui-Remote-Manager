"""Graphical setup wizard for the Windows PC controlling ComfyUI."""

import json
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from app.platform_paths import local_app_data_directory
from installer.python_runtime import find_python_executable, venv_is_usable

from installer.installer_common import (InstallerWindow, create_shortcut, desktop_directory, find_tailscale,
                                        open_tailscale, run_command, tailscale_ip,
                                        validate_config, winget_install, write_json)
from installer.layout import APP_FILES, ICON_PATH, resource_path


class ClientInstaller(InstallerWindow):
    def __init__(self):
        super().__init__("Installa PC Client · ComfyUI Remote Manager")
        self.source_mode = not getattr(sys, "frozen", False)
        self.install_dir = (resource_path() if self.source_mode else
                            local_app_data_directory() / "Programs" / "ComfyUIRemoteManager")
        self.app_dir = self.install_dir / "app"
        self.venv_dir = self.install_dir / ".venv"
        self.language_step(self.intro_step, 4)

    def intro_step(self):
        self.page("2 / 4 · Installa su PC Client",
                  "Installa ComfyUI Remote Manager e i componenti necessari.")
        self.label("Cartella di installazione: " + str(self.install_dir))
        self.button("Avvia installazione", self.start_install, primary=True)

    def start_install(self):
        self.run_async(self.install_components, lambda _result: self.tailscale_step())

    def find_python(self):
        return find_python_executable()

    def prepare_environment(self, python):
        root = self.install_dir.resolve()
        target = self.venv_dir.resolve()
        if target.parent != root or target.name != ".venv":
            raise RuntimeError("Percorso dell'ambiente Python non valido.")
        if not venv_is_usable(target):
            self.log("Preparazione dell'ambiente Python...")
            run_command([python, "-I", "-m", "venv", "--clear", str(target)], self.log)
        if not venv_is_usable(target):
            raise RuntimeError("Impossibile preparare un ambiente Python funzionante.")

    def install_components(self):
        if not find_tailscale():
            winget_install("Tailscale.Tailscale", self.log)
        if not find_tailscale():
            raise RuntimeError("Tailscale installato, ma l'eseguibile non è stato trovato. Riavvia l'installer.")
        self.log("Tailscale pronto.")

        python = self.find_python()
        if not python:
            winget_install("Python.Python.3.13", self.log)
            python = self.find_python()
        if not python:
            raise RuntimeError("Python installato, ma non trovato. Riavvia l'installer.")

        launcher = self.install_dir / "run.bat"
        icon_target = self.install_dir / ICON_PATH
        if not self.source_mode:
            self.app_dir.mkdir(parents=True, exist_ok=True)
            icon_target.parent.mkdir(parents=True, exist_ok=True)
            for name in APP_FILES:
                shutil.copy2(resource_path("app", name), self.app_dir / name)
            shutil.copy2(resource_path("run.bat"), launcher)
            shutil.copy2(resource_path(ICON_PATH), icon_target)

        venv_python = self.venv_dir / "Scripts" / "python.exe"
        self.prepare_environment(python)
        self.log("Installazione delle dipendenze Python...")
        run_command([str(venv_python), "-I", "-m", "pip", "install", "-r",
                     str(self.app_dir / "requirements.txt")], self.log)
        self.log("Programma installato.")

        desktop = desktop_directory()
        create_shortcut(desktop / "ComfyUI Remote Manager.lnk",
                        launcher, self.install_dir, icon_target)
        self.log("Collegamento sul Desktop creato.")
        self.save_language_preference()

    def preferences_path(self):
        return local_app_data_directory() / "ComfyUIRemoteManager" / "preferences.json"

    def save_language_preference(self):
        write_json(self.preferences_path(), {"language": self.language})

    def tailscale_step(self):
        self.page("3 / 4 · Accesso a Tailscale",
                  "Apri Tailscale e accedi con la stessa tailnet usata su PC Server. Torna qui e verifica la connessione prima di configurare l'app.")
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
        self.page("4 / 4 · Configura PC Server",
                  "Importa la configurazione, inserisci i dati a mano qui oppure direttamente nel programma.")
        self.button("Importa configurazione", self.import_config, primary=True)
        self.button("Inserisci a mano", self.manual_step)
        self.button("Chiudi", self.root.destroy)

    def profile_path(self):
        return local_app_data_directory() / "ComfyUIRemoteManager" / "connection.json"

    def save_profile(self, config):
        config = validate_config(config)
        profile = {key: config[key] for key in ("host", "port", "user", "comfy_dir",
                                                 "start_batch", "cloudflared_exe")}
        profile.update({"remember_password": False, "password": ""})
        write_json(self.profile_path(), profile)
        self.log("Configurazione salvata.")
        self.ready_step()

    def import_config(self):
        path = filedialog.askopenfilename(parent=self.root, title="Configurazione di PC Server",
                                          filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            config = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            self.save_profile(config)
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror("Configurazione", str(error), parent=self.root)

    def manual_step(self):
        self.page("4 / 4 · Inserimento manuale",
                  "Inserisci i dati di PC Server.")
        self.host_var = self.entry("Host o IP Tailscale di PC Server")
        self.user_var = self.entry("Utente Windows di PC Server")
        self.port_var = self.entry("Porta SSH", "22")
        self.comfy_var = self.entry("Cartella ComfyUI Portable su PC Server (es. C:\\ComfyUI)")
        self.batch_var = self.entry("Batch di avvio", "run_nvidia_gpu.bat")
        self.cloudflare_var = self.entry("Percorso cloudflared su PC Server",
                                        "cloudflared")
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
                  "Apri ComfyUI Remote Manager dal Desktop e connettiti a PC Server.")
        self.button("Chiudi", self.root.destroy)


if __name__ == "__main__":
    installer = ClientInstaller()
    if "--self-test" in sys.argv:
        installer.root.withdraw()
        assert all(resource_path("app", name).is_file() for name in APP_FILES)
        assert resource_path("run.bat").is_file()
        assert resource_path(ICON_PATH).is_file()
        installer.root.destroy()
    else:
        installer.root.mainloop()
