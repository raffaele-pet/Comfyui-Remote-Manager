"""Shared Tkinter UI and Windows setup helpers for the two installers."""

import ctypes
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from app.branding import apply_window_icon
from app.localization import set_active_language, translate, wrap_dialogs
from app.ui_theme import configure_dark_theme
from app.platform_paths import desktop_directory, local_app_data_directory, program_files_directory


BG = "#0f1623"
PANEL = "#151d2a"
TEXT = "#e8eef8"
MUTED = "#9aa8bd"
BLUE = "#2f81f7"
INPUT = "#0d1420"
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def run_command(args, log=None, timeout=None):
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace",
                               creationflags=FLAGS)
    lines = []
    expired = threading.Event()
    timer = None
    if timeout is not None:
        def stop_expired_process():
            if process.poll() is None:
                expired.set()
                process.kill()

        timer = threading.Timer(timeout, stop_expired_process)
        timer.start()
    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                lines.append(line)
                if log:
                    log(line)
        code = process.wait()
    except Exception:
        process.kill()
        process.wait()
        raise
    finally:
        if timer:
            timer.cancel()
    if expired.is_set():
        raise subprocess.TimeoutExpired(args, timeout)
    if code:
        raise RuntimeError(f"Comando non riuscito ({code}): {args[0]}\n" + "\n".join(lines[-5:]))
    return "\n".join(lines)


def winget_install(package_id, log):
    if not shutil.which("winget.exe"):
        raise RuntimeError("WinGet non trovato. Installa App Installer di Microsoft e riprova.")
    log(f"Installazione di {package_id}...")
    run_command(["winget.exe", "install", "--id", package_id, "--exact", "--source", "winget",
                 "--silent", "--accept-source-agreements", "--accept-package-agreements"], log)


def find_tailscale():
    path = program_files_directory() / "Tailscale" / "tailscale.exe"
    return str(path) if path.is_file() else shutil.which("tailscale.exe")


def find_cloudflared():
    command = shutil.which("cloudflared.exe")
    if command:
        return command
    program_files = program_files_directory()
    path = program_files / "Cloudflare" / "Cloudflared" / "cloudflared.exe"
    if path.is_file():
        return str(path)
    packages = local_app_data_directory() / "Microsoft" / "WinGet" / "Packages"
    if packages.is_dir():
        return next((str(path) for path in packages.glob("Cloudflare.cloudflared*/**/cloudflared.exe")), None)
    return None


def tailscale_ip():
    executable = find_tailscale()
    if not executable:
        return ""
    result = subprocess.run([executable, "ip", "-4"], capture_output=True, text=True,
                            creationflags=FLAGS, timeout=15)
    return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""


def open_tailscale():
    path = program_files_directory() / "Tailscale" / "tailscale-ipn.exe"
    if not path.is_file():
        raise RuntimeError("Interfaccia Tailscale non trovata. Aprila dal menu Start.")
    subprocess.Popen([str(path)], creationflags=FLAGS)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_config(config):
    import re
    if config.get("version") != 1:
        raise ValueError("Versione della configurazione non supportata.")
    host = str(config.get("host", "")).strip()
    user = str(config.get("user", "")).strip()
    comfy_dir = str(config.get("comfy_dir", "")).strip()
    start_batch = str(config.get("start_batch", "run_nvidia_gpu.bat")).strip()
    cloudflared = str(config.get("cloudflared_exe", "cloudflared")).strip()
    port = int(config.get("port", 22))
    if not host or any(char.isspace() for char in host) or not user or not 1 <= port <= 65535:
        raise ValueError("Host, utente o porta SSH non validi.")
    if not re.fullmatch(r"[A-Za-z]:\\[^\r\n]+", comfy_dir):
        raise ValueError("Inserisci il percorso Windows assoluto della cartella ComfyUI Portable.")
    if not re.fullmatch(r'[^<>:"/\\|?*\r\n]+\.bat', start_batch, re.IGNORECASE):
        raise ValueError("Il batch di avvio deve essere un file .bat nella cartella ComfyUI.")
    if not cloudflared or '"' in cloudflared or "\n" in cloudflared:
        raise ValueError("Percorso cloudflared non valido.")
    return {"version": 1, "host": host, "port": port, "user": user,
            "comfy_dir": comfy_dir, "start_batch": start_batch, "cloudflared_exe": cloudflared}


class InstallerWindow:
    def __init__(self, title):
        self.language = "en"
        self.window_title = title
        set_active_language(self.language)
        wrap_dialogs()
        self.root = tk.Tk()
        apply_window_icon(self.root)
        configure_dark_theme(self.root)
        self.root.title(self.t(title))
        self.root.geometry("790x620")
        self.root.minsize(690, 560)
        self.root.configure(bg=BG)
        self.events = queue.Queue()
        self.buttons = []

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(22, 12))
        self.heading = tk.Label(header, text=self.t(title), bg=BG, fg=TEXT,
                                font=("Segoe UI", 19, "bold"), anchor="w")
        self.heading.pack(fill="x")
        self.description = tk.Label(header, bg=BG, fg=MUTED, font=("Segoe UI", 10),
                                    justify="left", anchor="w", wraplength=730)
        self.description.pack(fill="x", pady=(6, 0))

        self.form = tk.Frame(self.root, bg=PANEL, padx=18, pady=14)
        self.form.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self.actions = tk.Frame(self.root, bg=BG)
        self.actions.pack(fill="x", padx=24, pady=(0, 8))
        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill="x", padx=24, pady=(0, 8))
        self.log_text = tk.Text(self.root, height=7, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                                relief="flat", state="disabled", wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="x", padx=24, pady=(0, 18))
        self.root.after(100, self._poll)

    def t(self, text):
        return translate(text, self.language)

    def language_step(self, next_step, total_steps):
        self.next_step = next_step
        self.page("Language", "Choose your language")
        self.heading.configure(text=f"1 / {total_steps} · Language / Lingua")
        self.description.configure(text="Choose your language / Scegli la lingua.")
        self.language_choice = tk.StringVar(value="en")
        for value, label in (("en", "English"), ("it", "Italiano")):
            tk.Radiobutton(self.form, text=label, value=value, variable=self.language_choice,
                           bg=PANEL, fg=TEXT, selectcolor=INPUT, activebackground=PANEL,
                           activeforeground=TEXT, font=("Segoe UI", 11)).pack(anchor="w", pady=6)
        self.button("Continue / Continua", self.continue_language, primary=True)

    def continue_language(self):
        self.language = self.language_choice.get()
        set_active_language(self.language)
        self.root.title(self.t(self.window_title))
        self.next_step()

    def page(self, heading, description):
        self.heading.configure(text=self.t(heading))
        self.description.configure(text=self.t(description))
        for widget in self.form.winfo_children():
            widget.destroy()
        for widget in self.actions.winfo_children():
            widget.destroy()
        self.buttons.clear()

    def label(self, text):
        label = tk.Label(self.form, text=self.t(text), bg=PANEL, fg=TEXT, font=("Segoe UI", 10),
                          justify="left", anchor="w", wraplength=710)
        label.pack(fill="x", pady=(4, 8))
        label.bind("<Configure>", lambda event: label.configure(wraplength=max(100, event.width)))

    def entry(self, label, value=""):
        self.label(label)
        variable = tk.StringVar(value=value)
        widget = tk.Entry(self.form, textvariable=variable, bg=INPUT, fg=TEXT,
                          insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        widget.pack(fill="x", ipady=6, pady=(0, 9))
        return variable

    def button(self, label, command, primary=False):
        button = tk.Button(self.actions, text=self.t(label), command=command,
                           bg=BLUE if primary else "#303a49", fg="white", relief="flat",
                           padx=14, pady=9, font=("Segoe UI", 9, "bold"))
        button.pack(side="left", padx=(0, 8))
        self.buttons.append(button)
        return button

    def log(self, message):
        self.events.put(("log", self.t(message)))

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def run_async(self, work, success):
        for button in self.buttons:
            button.configure(state="disabled")
        self.progress.start(12)

        def runner():
            try:
                result = work()
                self.events.put(("success", (success, result)))
            except Exception as error:
                self.events.put(("failure", str(error)))

        threading.Thread(target=runner, daemon=True).start()

    def _poll(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == "log":
                self._append_log(value)
            else:
                self.progress.stop()
                for button in self.buttons:
                    button.configure(state="normal")
                if kind == "success":
                    callback, result = value
                    callback(result)
                else:
                    messagebox.showerror("Installazione", value, parent=self.root)
                    self._append_log(self.t("ERRORE: " + value))
        self.root.after(100, self._poll)


def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def create_shortcut(link_path, target, working_directory, icon, arguments=""):
    """Create a Windows .lnk with Windows Script Host, then remove the temporary script."""
    def quote(value):
        return '"' + str(value).replace('"', '""') + '"'

    script = "\n".join([
        'Set shell = CreateObject("WScript.Shell")',
        f"Set link = shell.CreateShortcut({quote(link_path)})",
        f"link.TargetPath = {quote(target)}",
        f"link.Arguments = {quote(arguments)}",
        f"link.WorkingDirectory = {quote(working_directory)}",
        f"link.IconLocation = {quote(icon)}",
        "link.Save",
    ])
    with tempfile.NamedTemporaryFile("w", suffix=".vbs", encoding="utf-16", delete=False) as file:
        file.write(script)
        temp_path = file.name
    try:
        run_command(["cscript.exe", "//NoLogo", temp_path])
    finally:
        Path(temp_path).unlink(missing_ok=True)
