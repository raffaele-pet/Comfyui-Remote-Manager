"""Graphical setup wizard for the Windows PC hosting ComfyUI."""

import os
import re
import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from installer_common import (FLAGS, InstallerWindow, find_cloudflared, find_tailscale,
                              is_admin, open_tailscale, run_command, tailscale_ip,
                              validate_config, winget_install, write_json)


class ServerInstaller(InstallerWindow):
    def __init__(self):
        super().__init__("Installa Pc Server · ComfyUI Remote Manager")
        self.comfy_dir = ""
        self.start_batch = ""
        self.ssh_user = ""
        self.cloudflared_exe = ""
        self.host = ""
        self.language_step(self.choose_comfy, 5)

    def choose_comfy(self):
        self.page("2 / 5 · ComfyUI su Pc Server",
                  "Seleziona la cartella principale di ComfyUI Portable. Scegli il file batch che lo avvia e l'utente Windows da usare per SSH.")
        self.path_var = self.entry("Cartella ComfyUI Portable")
        browse = tk.Button(self.form, text=self.t("Sfoglia..."), command=self.browse_comfy,
                           bg="#303a49", fg="white", relief="flat", padx=12, pady=6)
        browse.pack(anchor="w", pady=(0, 8))
        self.label("Batch di avvio")
        self.batch_var = tk.StringVar()
        self.batch_box = ttk.Combobox(self.form, textvariable=self.batch_var, state="readonly")
        self.batch_box.pack(fill="x", pady=(0, 9))
        self.user_var = self.entry("Utente Windows per la connessione SSH", os.environ.get("USERNAME", ""))
        self.button("Installa componenti", self.start_install, primary=True)

    def browse_comfy(self):
        path = filedialog.askdirectory(title="Cartella ComfyUI Portable", parent=self.root)
        if not path:
            return
        self.path_var.set(path)
        batches = sorted(file.name for file in Path(path).glob("run*.bat") if file.is_file())
        self.batch_box.configure(values=batches)
        self.batch_var.set("run_nvidia_gpu.bat" if "run_nvidia_gpu.bat" in batches else
                           batches[0] if batches else "")

    def start_install(self):
        path = Path(self.path_var.get().strip())
        batch = self.batch_var.get().strip()
        user = self.user_var.get().strip()
        if not path.is_dir() or not (path / batch).is_file() or not (path / "python_embeded" / "python.exe").is_file():
            messagebox.showerror("ComfyUI", "Seleziona una cartella ComfyUI Portable con il batch scelto e python_embeded\\python.exe.", parent=self.root)
            return
        if not user:
            messagebox.showerror("Utente", "Inserisci l'utente Windows da usare per SSH.", parent=self.root)
            return
        if not is_admin():
            messagebox.showerror("Amministratore", "Riapri install-server.exe come amministratore.", parent=self.root)
            return
        self.comfy_dir = str(path.resolve())
        self.start_batch = batch
        self.ssh_user = user
        self.run_async(self.install_components, lambda _result: self.tailscale_step())

    def install_components(self):
        self.log("Verifica del server OpenSSH...")
        service = subprocess.run(["sc.exe", "query", "sshd"], capture_output=True,
                                 creationflags=FLAGS)
        if service.returncode:
            self.log("Installazione di OpenSSH Server...")
            run_command(["dism.exe", "/Online", "/Add-Capability",
                         "/CapabilityName:OpenSSH.Server~~~~0.0.1.0"], self.log)
        run_command(["sc.exe", "config", "sshd", "start=", "auto"], self.log)
        started = subprocess.run(["sc.exe", "query", "sshd"], capture_output=True,
                                 creationflags=FLAGS)
        if not re.search(rb":\s*4\s", started.stdout):
            run_command(["sc.exe", "start", "sshd"], self.log)
        firewall = subprocess.run(["netsh.exe", "advfirewall", "firewall", "show", "rule",
                                   "name=OpenSSH-Server-In-TCP"], capture_output=True,
                                  creationflags=FLAGS)
        if firewall.returncode:
            run_command(["netsh.exe", "advfirewall", "firewall", "add", "rule",
                         "name=OpenSSH-Server-In-TCP", "dir=in", "action=allow",
                         "protocol=TCP", "localport=22"], self.log)

        if not find_tailscale():
            winget_install("Tailscale.Tailscale", self.log)
        if not find_tailscale():
            raise RuntimeError("Tailscale installato, ma l'eseguibile non è stato trovato. Riavvia l'installer.")
        self.log("Tailscale pronto.")

        cloudflared = find_cloudflared()
        if not cloudflared:
            winget_install("Cloudflare.cloudflared", self.log)
            cloudflared = find_cloudflared()
        if not cloudflared:
            raise RuntimeError("cloudflared installato, ma l'eseguibile non è stato trovato. Riavvia l'installer.")
        bin_dir = Path(os.environ["PROGRAMDATA"]) / "ComfyUIRemoteManager"
        bin_dir.mkdir(parents=True, exist_ok=True)
        stable_path = bin_dir / "cloudflared.exe"
        if Path(cloudflared).resolve() != stable_path.resolve():
            shutil.copy2(cloudflared, stable_path)
        self.cloudflared_exe = str(stable_path)
        self.log("cloudflared pronto.")

    def tailscale_step(self):
        self.page("3 / 5 · Accesso a Tailscale",
                  "Apri Tailscale, accedi dal browser e usa la stessa tailnet che userai su Pc User. Torna qui e verifica la connessione.")
        self.label("Se l'icona Tailscale non appare, cercala nell'area di notifica di Windows.")
        self.button("Apri Tailscale", self.launch_tailscale)
        self.button("Verifica accesso", self.verify_tailscale, primary=True)

    def launch_tailscale(self):
        try:
            open_tailscale()
            self.log("Tailscale aperto. Completa l'accesso nel browser.")
        except Exception as error:
            messagebox.showerror("Tailscale", str(error), parent=self.root)

    def verify_tailscale(self):
        self.run_async(self.check_tailscale, self.tailscale_verified)

    def check_tailscale(self):
        host = tailscale_ip()
        if not host:
            raise RuntimeError("Nessun IP Tailscale rilevato. Completa l'accesso e riprova.")
        self.log("Accesso Tailscale verificato: " + host)
        try:
            run_command([find_tailscale(), "up", "--unattended=true"], self.log, timeout=30)
        except Exception:
            self.log("Run Unattended non attivato: puoi abilitarlo dal menu Tailscale.")
        return host

    def tailscale_verified(self, host):
        self.host = host
        self.cloudflare_step()

    def cloudflare_step(self):
        self.page("4 / 5 · Cloudflare",
                  "Il link pubblico apparirà nel programma dopo l'avvio di ComfyUI.")
        self.button("Verifica cloudflared", self.verify_cloudflared, primary=True)

    def verify_cloudflared(self):
        self.run_async(lambda: run_command([self.cloudflared_exe, "--version"], self.log),
                       lambda _result: self.save_step())

    def save_step(self):
        self.page("5 / 5 · Esporta configurazione",
                  "Salva il file di configurazione e copialo su Pc User. Contiene indirizzo, utente e percorsi; non contiene password.")
        self.label("Pc Server: " + self.host)
        self.label("Utente SSH: " + self.ssh_user)
        self.label("ComfyUI: " + self.comfy_dir + " · " + self.start_batch)
        self.button("Salva comfyui-remote-config.json", self.save_config, primary=True)
        self.button("Chiudi", self.root.destroy)

    def save_config(self):
        desktop = Path.home() / "Desktop"
        path = filedialog.asksaveasfilename(parent=self.root, title="Salva configurazione Pc Server",
                                             initialdir=str(desktop), initialfile="comfyui-remote-config.json",
                                             defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        config = validate_config({"version": 1, "host": self.host, "port": 22,
                                  "user": self.ssh_user, "comfy_dir": self.comfy_dir,
                                  "start_batch": self.start_batch,
                                  "cloudflared_exe": self.cloudflared_exe})
        write_json(path, config)
        self.log("Configurazione salvata: " + path)
        messagebox.showinfo("Pc Server pronto", "Copia questo file su Pc User. La password Windows verrà inserita nell'app su Pc User.", parent=self.root)


if __name__ == "__main__":
    ServerInstaller().root.mainloop()
