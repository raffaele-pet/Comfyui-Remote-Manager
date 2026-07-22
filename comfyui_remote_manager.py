import os
import re
import json
import base64
import errno
import ctypes
import posixpath
import queue
import threading
import time
import webbrowser
from io import BytesIO
from ctypes import wintypes
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageOps, ImageTk
except ModuleNotFoundError:
    Image = None
    ImageOps = None
    ImageTk = None

try:
    import paramiko
except ModuleNotFoundError:
    print("Paramiko non è installato. Installa con: py -m pip install paramiko")
    raise

# =========================================================
# CONFIGURAZIONE PC1
# =========================================================
DEFAULT_HOST = "100.111.231.116"
DEFAULT_USER = "tesi"

REMOTE_COMFY_DIR_WIN = r"C:\Users\tesi\Desktop\ComfyUI maggio 2026"
REMOTE_UPDATE_DIR_WIN = r"C:\Users\tesi\Desktop\ComfyUI maggio 2026\update"
REMOTE_DESKTOP_WIN = r"C:\Users\tesi\Desktop"

REMOTE_COMFY_DIR_SFTP = "/C:/Users/tesi/Desktop/ComfyUI maggio 2026"
REMOTE_DESKTOP_SFTP = "/C:/Users/tesi/Desktop"
REMOTE_CLOUDFLARE_OUTPUT_SFTP = "/C:/Users/tesi/Desktop/comfyui_cloudflared_output.txt"
REMOTE_CLOUDFLARE_LINK_SFTP = "/C:/Users/tesi/Desktop/comfyui_cloudflare_link.txt"
REMOTE_DOWNLOAD_HELPER_SFTP = "/C:/Users/tesi/Desktop/comfy_remote_download_helper.py"
REMOTE_DOWNLOAD_CONFIG_SFTP = "/C:/Users/tesi/Desktop/comfy_remote_download_config.json"
REMOTE_DOWNLOAD_HELPER_WIN = r"C:\Users\tesi\Desktop\comfy_remote_download_helper.py"

COMFY_PORT = 8188
COMFY_LOCAL_URL = "http://127.0.0.1:8188/system_stats"

# Comando di avvio ComfyUI verificato per PC1.
# Non usare la forma cmd /c ""C:\...\run_nvidia_gpu.bat"".
START_COMFY_CMD = rf'cd /d "{REMOTE_COMFY_DIR_WIN}" && run_nvidia_gpu.bat'
UPDATE_COMFY_CMD = rf'cd /d "{REMOTE_UPDATE_DIR_WIN}" && update_comfyui.bat'

# Stop compatto: chiude cloudflared e il processo in ascolto su 8188.
STOP_COMFY_CMD = (
    "powershell -NoProfile -Command "
    "\"$ErrorActionPreference='SilentlyContinue'; "
    "Stop-Process -Name cloudflared -Force; "
    f"$ids = Get-NetTCPConnection -LocalPort {COMFY_PORT} -State Listen | Select-Object -ExpandProperty OwningProcess -Unique; "
    "foreach ($procId in $ids) { Write-Output ('Chiudo processo sulla porta 8188: PID ' + $procId); Stop-Process -Id $procId -Force }; "
    "Start-Sleep -Seconds 2; "
    f"$left = Get-NetTCPConnection -LocalPort {COMFY_PORT} -State Listen; "
    "if ($left) { Write-Output 'PORTA_8188_OCCUPATA'; exit 1 } else { Write-Output 'PORTA_8188_LIBERA'; exit 0 }\""
)

KILL_CLOUDFLARED_CMD = r'taskkill /IM cloudflared.exe /F /T 2>nul'

STATUS_CMD = (
    "powershell -NoProfile -Command "
    "\"try { "
    f"$r = Invoke-WebRequest -UseBasicParsing -Uri '{COMFY_LOCAL_URL}' -TimeoutSec 3; "
    "if ($r.StatusCode -ge 200) { Write-Output 'RUNNING'; exit 0 } "
    "else { Write-Output 'STOPPED'; exit 1 } "
    "} catch { Write-Output 'STOPPED'; exit 1 }\""
)

DELETE_CLOUDFLARE_FILES_CMD = (
    rf'cd /d "{REMOTE_DESKTOP_WIN}" && '
    r'if exist comfyui_cloudflared_output.txt del /f /q comfyui_cloudflared_output.txt & '
    r'if exist comfyui_cloudflare_link.txt del /f /q comfyui_cloudflare_link.txt'
)

START_CLOUDFLARED_CMD = r'cloudflared tunnel --url http://127.0.0.1:8188'

URL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
TEXT_EXTENSIONS = {
    ".bat", ".cmd", ".conf", ".cfg", ".css", ".csv", ".env", ".gitignore",
    ".html", ".ini", ".js", ".json", ".log", ".md", ".ps1", ".py", ".sh",
    ".toml", ".ts", ".tsx", ".txt", ".xml", ".yaml", ".yml",
}
THUMBNAIL_MAX_FILE_SIZE = 64 * 1024 * 1024
REMOTE_TEXT_MAX_FILE_SIZE = 5 * 1024 * 1024
UPLOAD_FOLDER_EXCLUDED_DIRS = {".git"}
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ComfyUIRemoteManager"
CONNECTION_PROFILE_PATH = APP_DATA_DIR / "connection.json"


# =========================================================
# UI COLORS
# =========================================================
BG = "#0f1623"
PANEL = "#151d2a"
PANEL_2 = "#111927"
BORDER = "#293548"
TEXT = "#e8eef8"
MUTED = "#9aa8bd"
INPUT_BG = "#0d1420"
BLUE = "#2f81f7"
BLUE_HOVER = "#3b8cff"
GREEN = "#238636"
GREEN_HOVER = "#2ea043"
RED = "#da3633"
RED_HOVER = "#f85149"
YELLOW = "#d29922"
YELLOW_HOVER = "#e3b341"
DISABLED_BG = "#263143"
DISABLED_FG = "#708096"


class ComfyRemoteManager:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("PC2 → PC1 ComfyUI Remote Manager")
        self.root.geometry("1480x820")
        self.root.minsize(1180, 720)
        self.root.configure(bg=BG)

        self.client = None
        self.sftp = None
        self.connected = False
        self.busy = False
        self.comfy_status = "unknown"  # unknown, stopped, starting, updating, running, stopping
        self.current_remote_path = REMOTE_COMFY_DIR_SFTP
        self.current_link = ""
        self.remote_clipboard = None
        self.comfy_channel = None
        self.cloudflared_channel = None
        self._stop_monitor = False
        self._monitor_thread = None
        self.current_entries = []
        self.tree_item_data = {}
        self.icon_selected_index = None
        self.icon_image_items = {}
        self.icon_photo_refs = {}
        self.thumbnail_cache = {}
        self.thumbnail_generation = 0
        self._icon_resize_job = None
        self.terminal_sessions = []

        profile = self.load_connection_profile()
        saved_password = self.unprotect_password(profile.get("password", ""))
        default_user = profile.get("user", DEFAULT_USER)
        self.remote_home_path = f"/C:/Users/{default_user}"

        self.ui_queue = queue.Queue()

        self.host_var = StringVar(value=profile.get("host", DEFAULT_HOST))
        self.port_var = StringVar(value=str(profile.get("port", 22)))
        self.user_var = StringVar(value=default_user)
        self.password_var = StringVar(value=saved_password)
        self.remember_password_var = BooleanVar(value=bool(profile.get("remember_password", False)))
        self.host_summary_var = StringVar(value="")
        self.status_text_var = StringVar(value="ComfyUI: non connesso")
        self.link_var = StringVar(value="Nessun link disponibile")
        self.path_var = StringVar(value=self.current_remote_path)
        self.view_mode_var = StringVar(value="Dettagli")
        self.upload_progress_var = StringVar(value="Nessun trasferimento in corso")
        self.upload_progress_value = tk.DoubleVar(value=0.0)

        self.setup_styles()
        self.build_ui()
        for variable in (self.host_var, self.port_var, self.user_var):
            variable.trace_add("write", lambda *_args: self.refresh_host_summary())
        self.refresh_host_summary()
        self.root.after(100, self.process_ui_queue)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_buttons()

    # -----------------------------------------------------
    # PROFILO SSH LOCALE
    # -----------------------------------------------------
    def load_connection_profile(self):
        try:
            if CONNECTION_PROFILE_PATH.exists():
                with CONNECTION_PROFILE_PATH.open("r", encoding="utf-8") as profile_file:
                    data = json.load(profile_file)
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def protect_password(self, password):
        if not password:
            return ""

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = password.encode("utf-8")
        raw_buffer = ctypes.create_string_buffer(raw)
        input_blob = DataBlob(len(raw), ctypes.cast(raw_buffer, ctypes.POINTER(ctypes.c_byte)))
        output_blob = DataBlob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(input_blob),
            "ComfyUI Remote Manager",
            None,
            None,
            None,
            0,
            ctypes.byref(output_blob),
        ):
            raise ctypes.WinError()
        try:
            protected = ctypes.string_at(output_blob.pbData, output_blob.cbData)
            return base64.b64encode(protected).decode("ascii")
        finally:
            ctypes.windll.kernel32.LocalFree(output_blob.pbData)

    def unprotect_password(self, protected_password):
        if not protected_password:
            return ""
        try:
            class DataBlob(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

            protected = base64.b64decode(protected_password)
            protected_buffer = ctypes.create_string_buffer(protected)
            input_blob = DataBlob(
                len(protected),
                ctypes.cast(protected_buffer, ctypes.POINTER(ctypes.c_byte)),
            )
            output_blob = DataBlob()
            if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(input_blob),
                None,
                None,
                None,
                None,
                0,
                ctypes.byref(output_blob),
            ):
                return ""
            try:
                return ctypes.string_at(output_blob.pbData, output_blob.cbData).decode("utf-8")
            finally:
                ctypes.windll.kernel32.LocalFree(output_blob.pbData)
        except Exception:
            return ""

    def save_connection_profile(self, host, port, user, password, remember_password):
        try:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            profile = {
                "host": host,
                "port": port,
                "user": user,
                "remember_password": remember_password,
                "password": self.protect_password(password) if remember_password else "",
            }
            temporary_path = CONNECTION_PROFILE_PATH.with_suffix(".tmp")
            with temporary_path.open("w", encoding="utf-8") as profile_file:
                json.dump(profile, profile_file, indent=2)
            temporary_path.replace(CONNECTION_PROFILE_PATH)
        except Exception as error:
            self.enqueue("output", f"Profilo SSH non salvato: {error}")

    # -----------------------------------------------------
    # UI SETUP
    # -----------------------------------------------------
    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Treeview", background=PANEL_2, foreground=TEXT, fieldbackground=PANEL_2,
                        bordercolor=BORDER, rowheight=24)
        style.map("Treeview", background=[("selected", "#243b61")], foreground=[("selected", TEXT)])
        style.configure("Treeview.Heading", background="#1a2636", foreground=TEXT, relief="flat")
        style.configure("Vertical.TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BORDER, arrowcolor=TEXT)

    def panel(self, parent, title):
        frame = tk.LabelFrame(parent, text=title, bg=PANEL, fg=TEXT, bd=1, relief="solid",
                              labelanchor="nw", padx=8, pady=6, font=("Segoe UI", 9, "bold"))
        return frame

    def make_button(self, parent, text, command, bg, hover=None, width=None):
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg="white", activebackground=hover or bg,
                        activeforeground="white", disabledforeground=DISABLED_FG, bd=0, relief="flat",
                        padx=10, pady=6, cursor="hand2", font=("Segoe UI", 9, "bold"), width=width)

        def enter(_):
            if str(btn["state"]) != "disabled":
                btn.configure(bg=hover or bg)

        def leave(_):
            if str(btn["state"]) != "disabled":
                btn.configure(bg=bg)

        btn.bind("<Enter>", enter)
        btn.bind("<Leave>", leave)
        btn._normal_bg = bg
        btn._hover_bg = hover or bg
        return btn

    def set_button_enabled(self, btn, enabled: bool):
        if enabled:
            btn.configure(state="normal", bg=btn._normal_bg, cursor="hand2")
        else:
            btn.configure(state="disabled", bg=DISABLED_BG, cursor="arrow")

    def build_ssh_sidebar(self, parent):
        sidebar = tk.Frame(parent, bg="#0b1220", width=248, highlightthickness=1, highlightbackground=BORDER)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        title_row = tk.Frame(sidebar, bg="#0b1220")
        title_row.pack(fill="x", padx=14, pady=(14, 4))
        tk.Label(
            title_row,
            text="SSH PC1",
            bg="#0b1220",
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left")

        host_card = tk.Frame(sidebar, bg=PANEL, highlightthickness=1, highlightbackground=BORDER)
        host_card.pack(fill="x", padx=10, pady=(4, 10))
        card_top = tk.Frame(host_card, bg=PANEL)
        card_top.pack(fill="x", padx=10, pady=(9, 3))
        self.connection_status_dot = tk.Canvas(card_top, width=12, height=12, bg=PANEL, highlightthickness=0)
        self.connection_status_dot.pack(side="left", padx=(0, 7))
        self.connection_status_dot.create_oval(2, 2, 10, 10, fill="#6b7280", outline="#6b7280")
        tk.Label(card_top, text="pc-lavoro", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        self.conn_label = tk.Label(host_card, text="Non connesso", bg=PANEL, fg=MUTED,
                                   anchor="w", font=("Segoe UI", 8))
        self.conn_label.pack(fill="x", padx=10)
        tk.Label(host_card, textvariable=self.host_summary_var, bg=PANEL, fg="#7ea6d8",
                 anchor="w", font=("Consolas", 8)).pack(fill="x", padx=10, pady=(2, 9))

        self.sidebar_field(sidebar, "Host / IP Tailscale", self.host_var)
        connection_row = tk.Frame(sidebar, bg="#0b1220")
        connection_row.pack(fill="x", padx=10)
        self.sidebar_field(connection_row, "Utente", self.user_var, side="left", width=15)
        self.sidebar_field(connection_row, "Porta", self.port_var, side="left", width=6)
        self.sidebar_field(sidebar, "Password", self.password_var, show="*")

        remember = tk.Checkbutton(
            sidebar,
            text="Ricorda password su questo PC",
            variable=self.remember_password_var,
            bg="#0b1220",
            fg=MUTED,
            activebackground="#0b1220",
            activeforeground=TEXT,
            selectcolor=INPUT_BG,
            highlightthickness=0,
            font=("Segoe UI", 8),
        )
        remember.pack(anchor="w", padx=10, pady=(0, 8))

        button_row = tk.Frame(sidebar, bg="#0b1220")
        button_row.pack(fill="x", padx=10)
        self.btn_connect = self.make_button(button_row, "Connetti", self.connect, BLUE, BLUE_HOVER, width=9)
        self.btn_connect.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_disconnect = self.make_button(
            button_row, "Disconnetti", self.disconnect, "#303a49", "#3b4658", width=9
        )
        self.btn_disconnect.pack(side="left", fill="x", expand=True, padx=(3, 0))

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10, pady=14)
        tk.Label(sidebar, text="FILE REMOTI", bg="#0b1220", fg=MUTED,
                 anchor="w", font=("Segoe UI", 8, "bold")).pack(fill="x", padx=12, pady=(0, 5))

        self.sidebar_remote_buttons = []
        remote_actions = [
            ("⌂  Home utente", self.open_remote_home),
            ("▣  Desktop", self.open_remote_desktop),
        ]
        for label, command in remote_actions:
            button = self.make_button(sidebar, label, command, "#172235", "#22314a")
            button.configure(anchor="w")
            button.pack(fill="x", padx=10, pady=2)
            self.sidebar_remote_buttons.append(button)

        tk.Frame(sidebar, bg=BORDER, height=1).pack(fill="x", padx=10, pady=14)
        tk.Label(sidebar, text="STRUMENTI SSH", bg="#0b1220", fg=MUTED,
                 anchor="w", font=("Segoe UI", 8, "bold")).pack(fill="x", padx=12, pady=(0, 5))

        self.btn_ssh_terminal = self.make_button(
            sidebar,
            ">_  Terminale PowerShell",
            lambda: self.open_remote_terminal(self.remote_home_path),
            GREEN,
            GREEN_HOVER,
        )
        self.btn_ssh_terminal.configure(anchor="w")
        self.btn_ssh_terminal.pack(fill="x", padx=10, pady=2)
        self.sidebar_remote_buttons.append(self.btn_ssh_terminal)

        copy_command = self.make_button(
            sidebar,
            "⧉  Copia comando SSH",
            self.copy_ssh_command,
            "#303a49",
            "#3b4658",
        )
        copy_command.configure(anchor="w")
        copy_command.pack(fill="x", padx=10, pady=2)

        tk.Label(
            sidebar,
            text="La password ricordata è cifrata\ncon la protezione di Windows.",
            bg="#0b1220",
            fg="#64748b",
            justify="left",
            font=("Segoe UI", 7),
        ).pack(side="bottom", anchor="w", padx=12, pady=12)

    def sidebar_field(self, parent, label, variable, show=None, side="top", width=None):
        container = tk.Frame(parent, bg="#0b1220")
        if side == "left":
            container.pack(side="left", fill="x", expand=True, padx=(0, 5), pady=(0, 7))
        else:
            container.pack(fill="x", padx=10, pady=(0, 7))
        tk.Label(container, text=label, bg="#0b1220", fg=MUTED, anchor="w",
                 font=("Segoe UI", 8)).pack(fill="x", pady=(0, 2))
        entry = tk.Entry(
            container,
            textvariable=variable,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            show=show,
            width=width,
            font=("Segoe UI", 9),
        )
        entry.pack(fill="x", ipady=5)
        return entry

    def refresh_host_summary(self):
        host = self.host_var.get().strip() or "host"
        user = self.user_var.get().strip() or "utente"
        port = self.port_var.get().strip() or "22"
        self.host_summary_var.set(f"{user}@{host}:{port}")

    def draw_connection_status(self, connected):
        color = "#2ea043" if connected else "#6b7280"
        self.connection_status_dot.delete("all")
        self.connection_status_dot.create_oval(2, 2, 10, 10, fill=color, outline=color)

    def open_remote_home(self):
        self.open_folder(self.remote_home_path)

    def open_remote_desktop(self):
        self.open_folder(posixpath.join(self.remote_home_path.rstrip("/"), "Desktop"))

    def copy_ssh_command(self):
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        port = self.port_var.get().strip() or "22"
        if not host or not user:
            return
        command = f"ssh -p {port} {user}@{host}"
        self.root.clipboard_clear()
        self.root.clipboard_append(command)
        self.append_output(f"Comando copiato: {command}")

    def build_ui(self):
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        self.build_ssh_sidebar(shell)

        content = tk.Frame(shell, bg=BG)
        content.pack(side="left", fill="both", expand=True)

        header = tk.Frame(content, bg=BG)
        header.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(header, text="ComfyUI Remote Manager", bg=BG, fg=TEXT,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Avvia ComfyUI, genera il link pubblico e gestisci i file di PC1 da un'unica finestra.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        remote_controls = tk.Frame(content, bg=BG)
        remote_controls.pack(fill="x", padx=12, pady=3)

        actions = self.panel(remote_controls, "Azioni remote")
        actions.pack(side="left", fill="x", padx=(0, 4))
        ar = tk.Frame(actions, bg=PANEL)
        ar.pack(fill="x")
        self.btn_stop = self.make_button(ar, "⛔  Spegni", self.stop_comfyui, RED, RED_HOVER, width=12)
        self.btn_stop.pack(side="left", padx=(0, 4))
        self.btn_update = self.make_button(ar, "⬆  Aggiorna", self.update_comfyui, YELLOW, YELLOW_HOVER, width=12)
        self.btn_update.pack(side="left", padx=4)
        self.btn_start = self.make_button(ar, "🚀  Avvia", self.start_comfyui, GREEN, GREEN_HOVER, width=12)
        self.btn_start.pack(side="left", padx=4)

        self.status_box = tk.Frame(ar, bg=INPUT_BG, bd=1, relief="solid", highlightthickness=1, highlightbackground=BORDER)
        self.status_box.pack(side="left", padx=(8, 0), ipadx=10, ipady=5)
        self.status_dot = tk.Canvas(self.status_box, width=14, height=14, bg=INPUT_BG, highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = tk.Label(self.status_box, textvariable=self.status_text_var, bg=INPUT_BG, fg=TEXT,
                                     font=("Segoe UI", 9, "bold"))
        self.status_label.pack(side="left")
        self.draw_status_dot("#6b7280")

        link_panel = self.panel(remote_controls, "Link Cloudflare")
        link_panel.pack(side="left", fill="x", expand=True, padx=(4, 0))
        lr = tk.Frame(link_panel, bg=PANEL)
        lr.pack(fill="x")
        self.link_label = tk.Label(lr, textvariable=self.link_var, bg=INPUT_BG, fg="#58a6ff",
                                   anchor="w", padx=8, pady=7, cursor="hand2", font=("Segoe UI", 9, "underline"))
        self.link_label.pack(side="left", fill="x", expand=True)
        self.link_label.bind("<Button-1>", lambda _e: self.open_link())
        self.btn_open_link = self.make_button(lr, "Apri", self.open_link, "#303a49", "#3b4658", width=6)
        self.btn_open_link.pack(side="left", padx=(6, 3))
        self.btn_copy_link = self.make_button(lr, "Copia", self.copy_link, "#303a49", "#3b4658", width=6)
        self.btn_copy_link.pack(side="left", padx=(3, 0))

        main = tk.PanedWindow(
            content,
            orient="horizontal",
            bg=BG,
            bd=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        main.pack(fill="both", expand=True, padx=12, pady=(3, 12))

        browser = self.panel(main, "File browser remoto PC1")
        main.add(browser, minsize=650, stretch="always", width=1050, padx=0)

        brow_top = tk.Frame(browser, bg=PANEL)
        brow_top.pack(fill="x", pady=(0, 5))
        self.btn_up = self.make_button(brow_top, "⬆ Su", self.go_up, "#303a49", "#3b4658", width=7)
        self.btn_up.pack(side="left", padx=(0, 3))
        self.btn_refresh = self.make_button(brow_top, "Aggiorna", self.refresh_folder, "#303a49", "#3b4658", width=9)
        self.btn_refresh.pack(side="left", padx=3)
        self.btn_upload = self.make_button(brow_top, "Upload", self.show_upload_menu, BLUE, BLUE_HOVER, width=9)
        self.btn_upload.pack(side="left", padx=3)
        self.upload_menu = tk.Menu(
            self.btn_upload,
            tearoff=0,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#243b61",
            activeforeground=TEXT,
        )
        self.upload_menu.add_command(label="File...", command=self.upload_file)
        self.upload_menu.add_command(label="Cartella...", command=self.upload_folder)
        self.btn_download_url = self.make_button(brow_top, "Scarica URL", self.download_url_here, GREEN, GREEN_HOVER, width=12)
        self.btn_download_url.pack(side="left", padx=3)
        self.btn_terminal = self.make_button(
            brow_top,
            "Terminale",
            lambda: self.open_remote_terminal(self.current_remote_path),
            "#303a49",
            "#3b4658",
            width=10,
        )
        self.btn_terminal.pack(side="left", padx=3)
        self.view_button_text_var = StringVar(value="Visualizza: Dettagli")
        self.view_button = tk.Menubutton(
            brow_top,
            textvariable=self.view_button_text_var,
            bg="#303a49",
            fg=TEXT,
            activebackground="#3b4658",
            activeforeground=TEXT,
            disabledforeground=DISABLED_FG,
            bd=0,
            relief="flat",
            padx=10,
            pady=6,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            width=18,
        )
        view_menu = tk.Menu(
            self.view_button,
            tearoff=0,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#243b61",
            activeforeground=TEXT,
        )
        self.view_button.configure(menu=view_menu)
        for mode in ("Dettagli", "Elenco", "Icone piccole", "Icone medie", "Icone grandi"):
            view_menu.add_radiobutton(
                label=mode,
                value=mode,
                variable=self.view_mode_var,
                command=self.change_view_mode,
            )
        self.view_button.pack(side="right", padx=(6, 0))

        path_row = tk.Frame(browser, bg=PANEL)
        path_row.pack(fill="x", pady=(0, 5))
        tk.Label(path_row, text="Percorso", bg=PANEL, fg=MUTED, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        self.path_entry = tk.Entry(path_row, textvariable=self.path_var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                                   relief="flat")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=5)
        self.btn_go = self.make_button(path_row, "Vai", self.go_to_path, "#303a49", "#3b4658", width=6)
        self.btn_go.pack(side="left")

        shortcuts = tk.Frame(browser, bg=PANEL)
        shortcuts.pack(fill="x", pady=(0, 5))
        folder_shortcuts = [
            ("ComfyUI Portable", REMOTE_COMFY_DIR_SFTP),
            ("ComfyUI", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI"),
            ("custom nodes", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/custom_nodes"),
            ("models", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/models"),
            ("diffusion models", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/models/diffusion_models"),
            ("text encoders", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/models/text_encoders"),
            ("vae", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/models/vae"),
            ("loras", "/C:/Users/tesi/Desktop/ComfyUI maggio 2026/ComfyUI/models/loras"),
        ]
        for index, (label, path) in enumerate(folder_shortcuts):
            shortcuts.grid_columnconfigure(index, weight=1)
            b = self.make_button(shortcuts, label, lambda p=path: self.open_folder(p), "#253044", "#303c52")
            b.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 2, 0 if index == 7 else 2))

        self.file_view_area = tk.Frame(browser, bg=PANEL)
        self.file_view_area.pack(fill="both", expand=True)

        self.details_view = tk.Frame(self.file_view_area, bg=PANEL)
        self.details_view.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(self.details_view, columns=("name", "type", "size"), show="headings", selectmode="browse")
        self.tree.heading("name", text="Nome")
        self.tree.heading("type", text="Tipo")
        self.tree.heading("size", text="Dimensione")
        self.tree.column("#0", width=600, minwidth=260, anchor="w", stretch=True)
        self.tree.column("name", width=520, minwidth=260, anchor="w", stretch=True)
        self.tree.column("type", width=110, minwidth=90, anchor="center", stretch=False)
        self.tree.column("size", width=130, minwidth=100, anchor="e", stretch=False)
        self.tree.tag_configure("dir", foreground="#e8eef8")
        self.tree.tag_configure("file", foreground="#c9d7ea")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.file_context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=PANEL_2,
            fg=TEXT,
            activebackground="#243b61",
            activeforeground=TEXT,
            bd=1,
        )
        yscroll = ttk.Scrollbar(self.details_view, orient="vertical", command=self.tree.yview)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(self.details_view, orient="horizontal", command=self.tree.xview)
        xscroll.pack(side="bottom", fill="x")
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.icon_view = tk.Frame(self.file_view_area, bg=PANEL_2)
        self.icon_canvas = tk.Canvas(
            self.icon_view,
            bg=PANEL_2,
            highlightthickness=0,
            bd=0,
        )
        icon_scroll = ttk.Scrollbar(self.icon_view, orient="vertical", command=self.icon_canvas.yview)
        icon_scroll.pack(side="right", fill="y")
        self.icon_canvas.pack(side="left", fill="both", expand=True)
        self.icon_canvas.configure(yscrollcommand=icon_scroll.set)
        self.icon_canvas.bind("<Configure>", self.on_icon_canvas_resize)
        self.icon_canvas.bind("<Button-1>", self.on_icon_click)
        self.icon_canvas.bind("<Double-1>", self.on_icon_double_click)
        self.icon_canvas.bind("<Button-3>", self.on_icon_right_click)
        self.icon_canvas.bind(
            "<MouseWheel>",
            lambda event: self.icon_canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        upload_status = tk.Frame(browser, bg=PANEL)
        upload_status.pack(fill="x", pady=(5, 0))
        tk.Label(upload_status, textvariable=self.upload_progress_var, bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        self.upload_bar = ttk.Progressbar(upload_status, variable=self.upload_progress_value, maximum=100)
        self.upload_bar.pack(side="left", fill="x", expand=True)

        out_panel = self.panel(main, "Output")
        main.add(out_panel, minsize=260, stretch="never", width=330, padx=0)
        self.output = tk.Text(out_panel, bg="#080f1d", fg="#c9d7ea", insertbackground=TEXT,
                              relief="flat", wrap="word", font=("Consolas", 9), width=38)
        self.output.pack(fill="both", expand=True)

    def add_labeled_entry(self, parent, label, var, width=16, show=None):
        tk.Label(parent, text=label, bg=PANEL, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        e = tk.Entry(parent, textvariable=var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT,
                     relief="flat", width=width, show=show)
        e.pack(side="left", padx=(0, 10), ipady=5)
        return e

    # -----------------------------------------------------
    # UI HELPERS
    # -----------------------------------------------------
    def draw_status_dot(self, color):
        self.status_dot.delete("all")
        self.status_dot.create_oval(3, 3, 13, 13, fill=color, outline=color)

    def append_output(self, text):
        self.output.insert("end", text + "\n")
        self.output.see("end")

    def set_status(self, status):
        self.comfy_status = status
        if not self.connected:
            self.status_text_var.set("ComfyUI: non connesso")
            self.draw_status_dot("#6b7280")
        elif status == "running":
            self.status_text_var.set("ComfyUI: attivo")
            self.draw_status_dot("#2ea043")
        elif status == "starting":
            self.status_text_var.set("ComfyUI: avvio...")
            self.draw_status_dot("#d29922")
        elif status == "updating":
            self.status_text_var.set("ComfyUI: update...")
            self.draw_status_dot("#d29922")
        elif status == "stopping":
            self.status_text_var.set("ComfyUI: spegnimento...")
            self.draw_status_dot("#d29922")
        elif status == "stopped":
            self.status_text_var.set("ComfyUI: spento")
            self.draw_status_dot("#f85149")
        else:
            self.status_text_var.set("ComfyUI: stato sconosciuto")
            self.draw_status_dot("#6b7280")
        self.update_buttons()

    def update_buttons(self):
        connected = self.connected
        busy = self.busy
        running = self.comfy_status == "running"
        stopped = self.comfy_status in ("stopped", "unknown")
        updating = self.comfy_status == "updating"
        starting = self.comfy_status == "starting"
        stopping = self.comfy_status == "stopping"

        self.set_button_enabled(self.btn_connect, not connected and not busy)
        self.set_button_enabled(self.btn_disconnect, connected and not busy)
        for button in self.sidebar_remote_buttons:
            self.set_button_enabled(button, connected and not busy)

        # Regole richieste.
        # Modifica minima rispetto alla v13 funzionante:
        # il pulsante Spegni ComfyUI resta sempre cliccabile quando la connessione SSH è attiva,
        # anche durante avvio/update/busy, così puoi chiudere ComfyUI + tunnel in caso di blocco.
        self.set_button_enabled(self.btn_stop, connected)
        self.set_button_enabled(self.btn_update, connected and not running and not starting and not stopping)
        self.set_button_enabled(self.btn_start, connected and not running and not busy and not updating and not starting and not stopping)

        browser_enabled = connected and not busy
        for b in [self.btn_up, self.btn_refresh, self.btn_upload, self.btn_download_url, self.btn_go, self.btn_terminal]:
            self.set_button_enabled(b, browser_enabled)

        has_link = bool(self.current_link)
        self.set_button_enabled(self.btn_open_link, has_link)
        self.set_button_enabled(self.btn_copy_link, has_link)

    def enqueue(self, kind, *args):
        self.ui_queue.put((kind, args))

    def process_ui_queue(self):
        try:
            while True:
                kind, args = self.ui_queue.get_nowait()
                if kind == "output":
                    self.append_output(args[0])
                elif kind == "status":
                    self.set_status(args[0])
                elif kind == "busy":
                    self.busy = args[0]
                    self.update_buttons()
                elif kind == "connected":
                    self.connected = args[0]
                    self.conn_label.config(text=args[1] if len(args) > 1 else ("Connesso" if args[0] else "Non connesso"))
                    self.draw_connection_status(args[0])
                    self.update_buttons()
                elif kind == "remote_home":
                    self.remote_home_path = args[0]
                elif kind == "link":
                    self.current_link = args[0]
                    self.link_var.set(args[0] if args[0] else "Nessun link disponibile")
                    self.update_buttons()
                elif kind == "tree":
                    self.populate_tree(args[0])
                elif kind == "path":
                    self.current_remote_path = args[0]
                    self.path_var.set(args[0])
                elif kind == "upload_progress":
                    percent, text = args
                    self.upload_progress_value.set(percent)
                    self.upload_progress_var.set(text)
                elif kind == "error_dialog":
                    messagebox.showerror(args[0], args[1])
                elif kind == "info_dialog":
                    messagebox.showinfo(args[0], args[1])
                elif kind == "terminal_output":
                    terminal, text = args
                    self.append_terminal_output(terminal, text)
                elif kind == "terminal_done":
                    terminal = args[0]
                    self.finish_terminal_command(terminal)
                elif kind == "thumbnail":
                    generation, index, cache_key, image = args
                    self.apply_thumbnail(generation, index, cache_key, image)
                elif kind == "preview_image":
                    preview, image = args
                    self.apply_preview_image(preview, image)
                elif kind == "preview_error":
                    preview, error = args
                    self.show_preview_error(preview, error)
                elif kind == "editor_loaded":
                    editor, content, encoding = args
                    self.apply_remote_text(editor, content, encoding)
                elif kind == "editor_error":
                    editor, error = args
                    self.show_remote_editor_error(editor, error)
                elif kind == "editor_saved":
                    editor = args[0]
                    self.finish_remote_text_save(editor)
        except queue.Empty:
            pass
        self.root.after(100, self.process_ui_queue)

    # -----------------------------------------------------
    # SSH HELPERS
    # -----------------------------------------------------
    def connect(self):
        if self.connected:
            return
        host = self.host_var.get().strip()
        user = self.user_var.get().strip()
        password = self.password_var.get()
        remember_password = bool(self.remember_password_var.get())
        if not host or not user:
            messagebox.showwarning("Dati mancanti", "Inserisci host e utente.")
            return
        try:
            port = int(self.port_var.get().strip() or "22")
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Porta non valida", "Inserisci una porta SSH valida (1-65535).")
            return
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._connect_thread,
            args=(host, port, user, password, remember_password),
            daemon=True,
        ).start()

    def _connect_thread(self, host, port, user, password, remember_password):
        try:
            self.enqueue("output", f"Connessione SSH a {user}@{host}:{port}...")
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=host,
                port=port,
                username=user,
                password=password or None,
                timeout=15,
                banner_timeout=20,
                auth_timeout=20,
                look_for_keys=True,
                allow_agent=True,
            )
            sftp = client.open_sftp()
            self.client = client
            self.sftp = sftp
            self.connected = True
            try:
                remote_home = self.normalize_sftp_path(sftp.normalize("."))
            except Exception:
                remote_home = f"/C:/Users/{user}"
            self.enqueue("remote_home", remote_home)
            self.save_connection_profile(host, port, user, password, remember_password)
            self.enqueue("connected", True, f"Connesso a {user}@{host}:{port}")
            self.enqueue("output", "Connessione riuscita.")
            self.enqueue("busy", False)
            self.check_status_async()
            self.open_folder(remote_home)
            self.start_status_monitor()
        except Exception as e:
            self.client = None
            self.sftp = None
            self.connected = False
            self.enqueue("connected", False, "Non connesso")
            self.enqueue("busy", False)
            self.enqueue("status", "unknown")
            self.enqueue("error_dialog", "Errore connessione", str(e))

    def disconnect(self):
        self._stop_monitor = True
        self.busy = False
        for terminal in list(self.terminal_sessions):
            self.close_remote_terminal(terminal)
        try:
            self.close_remote_channels()
        except Exception:
            pass
        try:
            if self.sftp:
                self.sftp.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.sftp = None
        self.client = None
        self.connected = False
        self.remote_clipboard = None
        self.current_entries = []
        self.icon_selected_index = None
        self.thumbnail_generation += 1
        self.thumbnail_cache.clear()
        self.current_link = ""
        self.link_var.set("Nessun link disponibile")
        self.conn_label.config(text="Non connesso")
        self.draw_connection_status(False)
        self.set_status("unknown")
        try:
            self.tree.delete(*self.tree.get_children())
            self.icon_canvas.delete("all")
        except Exception:
            pass
        self.append_output("Disconnesso.")
        self.update_buttons()

    def ensure_connected(self):
        return self.connected and self.client is not None

    def run_command(self, command, title=None, timeout=None, stream=False, stop_on_done=False):
        if not self.ensure_connected():
            raise RuntimeError("Non connesso a PC1.")

        if title:
            self.enqueue("output", f"\n=== {title} ===")
        self.enqueue("output", f"> {command}")

        stdin, stdout, stderr = self.client.exec_command(command, get_pty=False, timeout=timeout)
        chan = stdout.channel

        if not stream:
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = chan.recv_exit_status()
            if out.strip():
                self.enqueue("output", out.rstrip())
            if err.strip():
                self.enqueue("output", err.rstrip())
            self.enqueue("output", f"Exit code: {code}")
            return code, out, err

        # Streaming non bloccante, utile per update.
        output_parts = []
        done_seen = False
        start_time = time.time()
        while True:
            if stdout.channel.recv_ready():
                data = stdout.channel.recv(4096).decode("utf-8", errors="replace")
                if data:
                    output_parts.append(data)
                    self.enqueue("output", data.rstrip())
                    for line in data.splitlines():
                        clean_line = line.strip()
                        if clean_line.startswith("DOWNLOAD_PROGRESS"):
                            m = re.search(r"DOWNLOAD_PROGRESS\s+([0-9.]+)%", clean_line)
                            if m:
                                try:
                                    self.enqueue("upload_progress", float(m.group(1)), clean_line.replace("DOWNLOAD_PROGRESS ", "Download remoto: "))
                                except Exception:
                                    pass
                            else:
                                self.enqueue("upload_progress", 0.0, clean_line.replace("DOWNLOAD_PROGRESS ", "Download remoto: "))
                    if stop_on_done and "Done!" in data:
                        done_seen = True
            if stdout.channel.recv_stderr_ready():
                data = stdout.channel.recv_stderr(4096).decode("utf-8", errors="replace")
                if data:
                    output_parts.append(data)
                    self.enqueue("output", data.rstrip())
                    for line in data.splitlines():
                        clean_line = line.strip()
                        if clean_line.startswith("DOWNLOAD_PROGRESS"):
                            m = re.search(r"DOWNLOAD_PROGRESS\s+([0-9.]+)%", clean_line)
                            if m:
                                try:
                                    self.enqueue("upload_progress", float(m.group(1)), clean_line.replace("DOWNLOAD_PROGRESS ", "Download remoto: "))
                                except Exception:
                                    pass
                            else:
                                self.enqueue("upload_progress", 0.0, clean_line.replace("DOWNLOAD_PROGRESS ", "Download remoto: "))
                    if stop_on_done and "Done!" in data:
                        done_seen = True

            if chan.exit_status_ready():
                code = chan.recv_exit_status()
                self.enqueue("output", f"Exit code: {code}")
                return code, "".join(output_parts), ""

            if done_seen:
                # Alcuni bat rimangono aperti: appena c'è Done!, chiudiamo il canale remoto.
                time.sleep(0.5)
                try:
                    chan.close()
                except Exception:
                    pass
                self.enqueue("output", "Update concluso: rilevato Done!.")
                return 0, "".join(output_parts), ""

            if timeout and time.time() - start_time > timeout:
                try:
                    chan.close()
                except Exception:
                    pass
                self.enqueue("output", "Timeout comando.")
                return 124, "".join(output_parts), ""

            time.sleep(0.1)

    def run_command_quiet(self, command, timeout=None):
        if not self.ensure_connected():
            raise RuntimeError("Non connesso a PC1.")
        stdin, stdout, stderr = self.client.exec_command(command, get_pty=False, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        code = stdout.channel.recv_exit_status()
        return code, out, err

    def close_remote_channels(self):
        for attr in ("cloudflared_channel", "comfy_channel"):
            ch = getattr(self, attr, None)
            if ch is not None:
                try:
                    ch.close()
                except Exception:
                    pass
                setattr(self, attr, None)

    def start_long_running_command(self, command, title, channel_attr, on_url=False):
        if not self.ensure_connected():
            raise RuntimeError("Non connesso a PC1.")
        self.enqueue("output", f"\n=== {title} ===")
        self.enqueue("output", f"> {command}")
        transport = self.client.get_transport()
        if not transport or not transport.is_active():
            raise RuntimeError("Connessione SSH non attiva.")
        chan = transport.open_session()
        chan.set_combine_stderr(True)
        chan.exec_command(command)
        setattr(self, channel_attr, chan)
        thread = threading.Thread(
            target=self._long_running_reader,
            args=(chan, title, channel_attr, on_url),
            daemon=True,
        )
        thread.start()
        return chan

    def _long_running_reader(self, chan, title, channel_attr, on_url):
        buffer = ""
        try:
            while True:
                if chan.recv_ready():
                    data = chan.recv(4096).decode("utf-8", errors="replace")
                    if data:
                        buffer += data
                        # Per ComfyUI evitiamo di intasare troppo l'output: mostriamo solo righe significative.
                        for line in data.splitlines():
                            clean = line.strip()
                            if not clean:
                                continue
                            if on_url:
                                self.enqueue("output", f"[cloudflared] {clean}")
                            elif any(key in clean.lower() for key in ("starting server", "to see the gui", "error", "traceback", "failed", "port", "database")):
                                self.enqueue("output", f"[ComfyUI] {clean}")
                        if on_url:
                            match = URL_RE.search(buffer)
                            if match:
                                url = match.group(0)
                                self.enqueue("link", url)
                                self.enqueue("output", f"Link Cloudflare generato: {url}")
                                self.write_remote_link_file(url)
                if chan.exit_status_ready():
                    code = chan.recv_exit_status()
                    self.enqueue("output", f"{title} terminato. Exit code: {code}")
                    current = getattr(self, channel_attr, None)
                    if current is chan:
                        setattr(self, channel_attr, None)
                    break
                time.sleep(0.2)
        except Exception as e:
            self.enqueue("output", f"Errore lettura {title}: {e}")
            current = getattr(self, channel_attr, None)
            if current is chan:
                setattr(self, channel_attr, None)

    # -----------------------------------------------------
    # STATUS MONITOR
    # -----------------------------------------------------
    def start_status_monitor(self):
        self._stop_monitor = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_thread = threading.Thread(target=self._status_monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _status_monitor_loop(self):
        while not self._stop_monitor:
            time.sleep(8)
            if self.connected and not self.busy and self.comfy_status not in ("starting", "updating", "stopping"):
                try:
                    running = self.remote_is_comfy_running()
                    self.enqueue("status", "running" if running else "stopped")
                except Exception:
                    pass

    def check_status_async(self):
        threading.Thread(target=self._check_status_thread, daemon=True).start()

    def _check_status_thread(self):
        try:
            running = self.remote_is_comfy_running()
            self.enqueue("status", "running" if running else "stopped")
        except Exception:
            self.enqueue("status", "unknown")

    def remote_is_comfy_running(self):
        code, out, err = self.run_command_quiet(STATUS_CMD, timeout=8)
        return "RUNNING" in (out + err) or code == 0

    # -----------------------------------------------------
    # ACTIONS
    # -----------------------------------------------------
    def stop_comfyui(self):
        if not self.ensure_connected():
            return
        self.busy = True
        self.set_status("stopping")
        threading.Thread(target=self._stop_thread, daemon=True).start()

    def _stop_thread(self):
        try:
            self.run_command(STOP_COMFY_CMD, title="SPEGNI COMFYUI", timeout=30)
            self.close_remote_channels()
            time.sleep(1)
            running = self.remote_is_comfy_running()
            self.enqueue("status", "running" if running else "stopped")
            if running:
                self.enqueue("output", "ATTENZIONE: ComfyUI risponde ancora su 8188.")
            else:
                self.enqueue("output", "OK: ComfyUI spento.")
            self.enqueue("link", "")
        except Exception as e:
            self.enqueue("output", f"Errore spegnimento: {e}")
        finally:
            self.enqueue("busy", False)

    def update_comfyui(self):
        if not self.ensure_connected():
            return
        if self.comfy_status == "running":
            messagebox.showwarning("ComfyUI attivo", "Spegni ComfyUI prima di fare update.")
            return
        self.busy = True
        self.set_status("updating")
        threading.Thread(target=self._update_thread, daemon=True).start()

    def _update_thread(self):
        try:
            self.run_command(UPDATE_COMFY_CMD, title="UPDATE COMFYUI", timeout=20 * 60, stream=True, stop_on_done=True)
            running = self.remote_is_comfy_running()
            self.enqueue("status", "running" if running else "stopped")
        except Exception as e:
            self.enqueue("output", f"Errore update: {e}")
            self.enqueue("status", "stopped")
        finally:
            self.enqueue("busy", False)

    def start_comfyui(self):
        if not self.ensure_connected():
            return
        self.busy = True
        self.set_status("starting")
        self.enqueue("link", "")
        threading.Thread(target=self._start_thread, daemon=True).start()

    def _start_thread(self):
        try:
            # Chiudiamo solo cloudflared vecchio. Non usiamo start "" e non stacchiamo ComfyUI:
            # teniamo il bat vivo in un canale SSH separato, così parte davvero come quando lo lanci a mano.
            self.run_command(KILL_CLOUDFLARED_CMD, title="CHIUDI CLOUDFLARED PRECEDENTE", timeout=15)

            if self.remote_is_comfy_running():
                self.enqueue("output", "ComfyUI risulta già attivo. Non lo rilancio.")
                self.enqueue("status", "running")
            else:
                self.start_long_running_command(START_COMFY_CMD, "AVVIA COMFYUI", "comfy_channel", on_url=False)
                if not self.wait_for_comfyui(timeout_seconds=15 * 60):
                    self.enqueue("status", "stopped")
                    self.enqueue("output", "ERRORE: ComfyUI non è diventato attivo entro il timeout.")
                    return
                self.enqueue("status", "running")

            # Avvio cloudflared in un secondo canale SSH persistente e leggo direttamente stdout/stderr.
            # Questo evita il blocco della GUI e non dipende da redirect su file.
            self.start_long_running_command(START_CLOUDFLARED_CMD, "AVVIA CLOUDFLARED", "cloudflared_channel", on_url=True)

            if not self.wait_for_link_in_memory(timeout_seconds=180):
                self.enqueue("output", "ERRORE: cloudflared non ha generato un link entro il timeout.")
        except Exception as e:
            self.enqueue("output", f"Errore avvio: {e}")
            self.enqueue("status", "stopped")
        finally:
            self.enqueue("busy", False)

    def wait_for_comfyui(self, timeout_seconds=900):
        self.enqueue("output", "Attendo ComfyUI sulla porta 8188...")
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                if self.remote_is_comfy_running():
                    self.enqueue("output", "OK: ComfyUI è attivo.")
                    return True
            except Exception:
                pass
            elapsed = int(time.time() - start)
            self.enqueue("output", f"ComfyUI non ancora pronto... {elapsed}s")
            time.sleep(5)
        return False

    def wait_for_link_in_memory(self, timeout_seconds=180):
        self.enqueue("output", "Attendo il link trycloudflare...")
        start = time.time()
        while time.time() - start < timeout_seconds:
            if self.current_link:
                return True
            ch = self.cloudflared_channel
            if ch is not None and ch.exit_status_ready():
                return bool(self.current_link)
            time.sleep(1)
        return bool(self.current_link)

    def wait_for_cloudflare_url(self, timeout_seconds=180):
        self.enqueue("output", "Attendo il link trycloudflare dal file remoto...")
        start = time.time()
        last_size = -1
        while time.time() - start < timeout_seconds:
            try:
                text = self.read_remote_text_file(REMOTE_CLOUDFLARE_OUTPUT_SFTP)
                match = URL_RE.search(text or "")
                if match:
                    return match.group(0)
                # Mostriamo solo se il file cresce, senza invadere l'output.
                if text and len(text) != last_size:
                    last_size = len(text)
                    tail = "\n".join(text.splitlines()[-6:])
                    if tail.strip():
                        self.enqueue("output", "[cloudflared output]\n" + tail)
            except FileNotFoundError:
                pass
            except IOError:
                pass
            time.sleep(2)
        return None

    def read_remote_text_file(self, sftp_path):
        if not self.sftp:
            return ""
        with self.sftp.open(sftp_path, "r") as f:
            data = f.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return data

    def write_remote_link_file(self, url):
        try:
            with self.sftp.open(REMOTE_CLOUDFLARE_LINK_SFTP, "w") as f:
                f.write(url)
        except Exception as e:
            self.enqueue("output", f"Non riesco a scrivere il file link remoto: {e}")

    # -----------------------------------------------------
    # FILE BROWSER
    # -----------------------------------------------------
    def normalize_sftp_path(self, path):
        path = path.strip().replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", path):
            path = "/" + path
        if path.startswith("C:/"):
            path = "/" + path
        return path.rstrip("/") if len(path) > 4 else path

    def open_folder(self, path):
        if not self.connected or not self.sftp:
            return
        path = self.normalize_sftp_path(path)
        threading.Thread(target=self._open_folder_thread, args=(path,), daemon=True).start()

    def _open_folder_thread(self, path):
        try:
            entries = []
            for attr in self.sftp.listdir_attr(path):
                name = attr.filename
                if name in (".", ".."):
                    continue
                is_dir = self.is_dir_attr(attr)
                size = "" if is_dir else self.format_size(attr.st_size)
                entries.append(
                    {
                        "name": name,
                        "type": "Cartella" if is_dir else "File",
                        "size": size,
                        "is_dir": is_dir,
                        "raw_size": attr.st_size,
                        "mtime": attr.st_mtime,
                        "path": posixpath.join(path.rstrip("/"), name),
                    }
                )
            entries.sort(key=lambda entry: (not entry["is_dir"], entry["name"].lower()))
            self.enqueue("path", path)
            self.enqueue("tree", entries)
            self.enqueue("output", f"Cartella aperta: {path}")
        except Exception as e:
            if self.connected:
                self.enqueue("output", f"Impossibile aprire cartella {path}: {e}")

    def populate_tree(self, entries):
        self.current_entries = entries
        self.icon_selected_index = None
        self.thumbnail_generation += 1
        self.render_current_view()

    def change_view_mode(self):
        mode = self.view_mode_var.get()
        self.view_button_text_var.set(f"Visualizza: {mode}")
        self.render_current_view()

    def render_current_view(self):
        mode = self.view_mode_var.get()
        if mode in ("Dettagli", "Elenco"):
            self.icon_view.pack_forget()
            if not self.details_view.winfo_manager():
                self.details_view.pack(fill="both", expand=True)
            self.render_tree_view(mode)
        else:
            self.details_view.pack_forget()
            if not self.icon_view.winfo_manager():
                self.icon_view.pack(fill="both", expand=True)
            self.root.after_idle(self.render_icon_view)

    def render_tree_view(self, mode):
        self.tree.delete(*self.tree.get_children())
        self.tree_item_data = {}
        self.tree.configure(show="headings" if mode == "Dettagli" else "tree")
        for index, entry in enumerate(self.current_entries):
            prefix = "📁 " if entry["is_dir"] else "📄 "
            item_id = self.tree.insert(
                "",
                "end",
                text=prefix + entry["name"],
                values=(prefix + entry["name"], entry["type"], entry["size"]),
                tags=("dir" if entry["is_dir"] else "file",),
            )
            self.tree_item_data[item_id] = entry

    def icon_layout(self):
        mode = self.view_mode_var.get()
        if mode == "Icone piccole":
            return 48, 116, 110
        if mode == "Icone medie":
            return 96, 160, 165
        return 160, 226, 238

    def render_icon_view(self):
        if not self.view_mode_var.get().startswith("Icone"):
            return
        canvas = self.icon_canvas
        canvas.delete("all")
        self.icon_image_items = {}
        self.icon_photo_refs = {}
        self.icon_selection_items = {}
        self.icon_selected_index = None
        self.thumbnail_generation += 1
        generation = self.thumbnail_generation

        thumb_size, tile_width, tile_height = self.icon_layout()
        canvas_width = max(canvas.winfo_width(), tile_width)
        columns = max(1, canvas_width // tile_width)
        horizontal_margin = max(4, (canvas_width - columns * tile_width) // 2)
        thumbnail_jobs = []

        for index, entry in enumerate(self.current_entries):
            row, column = divmod(index, columns)
            left = horizontal_margin + column * tile_width + 4
            top = row * tile_height + 4
            right = left + tile_width - 8
            bottom = top + tile_height - 8
            tag = f"entry_{index}"

            selection_item = canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=PANEL_2,
                outline=PANEL_2,
                width=1,
                tags=("entry", tag),
            )
            self.icon_selection_items[index] = selection_item

            image_center_y = top + 8 + thumb_size / 2
            if entry["is_dir"]:
                canvas.create_text(
                    (left + right) / 2,
                    image_center_y,
                    text="📁",
                    fill="#e8eef8",
                    font=("Segoe UI Emoji", max(24, int(thumb_size * 0.55))),
                    tags=("entry", tag),
                )
            elif self.is_image_file(entry["name"]) and Image is not None:
                placeholder = canvas.create_rectangle(
                    (left + right - thumb_size) / 2,
                    top + 8,
                    (left + right + thumb_size) / 2,
                    top + 8 + thumb_size,
                    fill="#0d1420",
                    outline=BORDER,
                    tags=("entry", tag),
                )
                image_item = canvas.create_image(
                    (left + right) / 2,
                    image_center_y,
                    tags=("entry", tag),
                )
                self.icon_image_items[index] = image_item
                cache_key = (entry["path"], entry["mtime"], thumb_size)
                cached = self.thumbnail_cache.get(cache_key)
                if cached:
                    canvas.itemconfigure(placeholder, state="hidden")
                    canvas.itemconfigure(image_item, image=cached)
                    self.icon_photo_refs[index] = cached
                elif entry["raw_size"] <= THUMBNAIL_MAX_FILE_SIZE:
                    thumbnail_jobs.append((index, entry, cache_key, thumb_size, placeholder))
            else:
                canvas.create_text(
                    (left + right) / 2,
                    image_center_y,
                    text="📄",
                    fill="#c9d7ea",
                    font=("Segoe UI Emoji", max(22, int(thumb_size * 0.5))),
                    tags=("entry", tag),
                )

            text_y = top + thumb_size + 16
            canvas.create_text(
                (left + right) / 2,
                text_y,
                text=entry["name"],
                fill=TEXT,
                width=tile_width - 18,
                anchor="n",
                justify="center",
                font=("Segoe UI", 8 if thumb_size == 48 else 9),
                tags=("entry", tag),
            )

        rows = (len(self.current_entries) + columns - 1) // columns
        canvas.configure(scrollregion=(0, 0, canvas_width, max(rows * tile_height + 4, canvas.winfo_height())))
        canvas.yview_moveto(0)

        if thumbnail_jobs:
            threading.Thread(
                target=self._thumbnail_loader_thread,
                args=(generation, thumbnail_jobs),
                daemon=True,
            ).start()

    def _thumbnail_loader_thread(self, generation, jobs):
        thumbnail_sftp = None
        try:
            if not self.ensure_connected() or Image is None:
                return
            thumbnail_sftp = self.client.open_sftp()
            for index, entry, cache_key, thumb_size, placeholder in jobs:
                if generation != self.thumbnail_generation or not self.connected:
                    break
                try:
                    with thumbnail_sftp.open(entry["path"], "rb") as remote_file:
                        data = remote_file.read()
                    image = Image.open(BytesIO(data))
                    image = ImageOps.exif_transpose(image)
                    image.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
                    image = image.convert("RGBA")
                    self.enqueue("thumbnail", generation, index, cache_key, image)
                except Exception:
                    continue
        finally:
            if thumbnail_sftp:
                try:
                    thumbnail_sftp.close()
                except Exception:
                    pass

    def apply_thumbnail(self, generation, index, cache_key, image):
        if generation != self.thumbnail_generation or not self.icon_canvas.winfo_exists():
            return
        image_item = self.icon_image_items.get(index)
        if not image_item:
            return
        photo = ImageTk.PhotoImage(image)
        self.thumbnail_cache[cache_key] = photo
        while len(self.thumbnail_cache) > 300:
            self.thumbnail_cache.pop(next(iter(self.thumbnail_cache)))
        self.icon_photo_refs[index] = photo
        self.icon_canvas.itemconfigure(image_item, image=photo)

    def on_icon_canvas_resize(self, _event):
        if not self.view_mode_var.get().startswith("Icone"):
            return
        if self._icon_resize_job:
            try:
                self.root.after_cancel(self._icon_resize_job)
            except Exception:
                pass
        self._icon_resize_job = self.root.after(150, self.render_icon_view)

    def icon_index_at(self, event):
        items = self.icon_canvas.find_withtag("current")
        if not items:
            return None
        for tag in self.icon_canvas.gettags(items[0]):
            if tag.startswith("entry_"):
                try:
                    return int(tag.split("_", 1)[1])
                except ValueError:
                    return None
        return None

    def select_icon_index(self, index):
        self.icon_selected_index = index
        for item_index, rectangle in self.icon_selection_items.items():
            selected = item_index == index
            self.icon_canvas.itemconfigure(
                rectangle,
                fill="#243b61" if selected else PANEL_2,
                outline="#3b82f6" if selected else PANEL_2,
            )

    def on_icon_click(self, event):
        self.select_icon_index(self.icon_index_at(event))

    def on_icon_double_click(self, event):
        index = self.icon_index_at(event)
        if index is None:
            return
        self.select_icon_index(index)
        self.open_or_preview_item(self.selected_remote_item())

    def on_icon_right_click(self, event):
        if not self.connected or not self.sftp or self.busy:
            return
        self.select_icon_index(self.icon_index_at(event))
        self.show_file_context_menu(event.x_root, event.y_root)

    def is_dir_attr(self, attr):
        import stat
        return stat.S_ISDIR(attr.st_mode)

    def format_size(self, size):
        size = float(size)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024:
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"

    def format_seconds(self, seconds):
        seconds = max(int(seconds), 0)
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"

    def refresh_folder(self):
        self.open_folder(self.current_remote_path)

    def go_to_path(self):
        self.open_folder(self.path_var.get())

    def go_up(self):
        path = self.normalize_sftp_path(self.current_remote_path)
        if path.count("/") <= 2:
            return
        parent = path.rsplit("/", 1)[0]
        self.open_folder(parent)

    def on_tree_double_click(self, _event):
        self.open_or_preview_item(self.selected_remote_item())

    def selected_remote_item(self):
        if self.view_mode_var.get().startswith("Icone"):
            index = self.icon_selected_index
            if index is None or not 0 <= index < len(self.current_entries):
                return None
            return dict(self.current_entries[index])

        selection = self.tree.selection()
        if not selection:
            return None
        entry = self.tree_item_data.get(selection[0])
        return dict(entry) if entry else None

    def is_image_file(self, name):
        return Path(name).suffix.lower() in IMAGE_EXTENSIONS

    def is_text_file(self, name):
        lower_name = name.lower()
        return (
            Path(lower_name).suffix in TEXT_EXTENSIONS
            or lower_name in {"dockerfile", "license", "makefile", "readme", ".gitignore", ".gitattributes"}
        )

    def open_or_preview_item(self, item):
        if not item:
            return
        if item["is_dir"]:
            self.open_folder(item["path"])
        elif self.is_image_file(item["name"]):
            self.preview_remote_image(item)
        elif self.is_text_file(item["name"]):
            self.edit_remote_text_file(item)

    def on_tree_right_click(self, event):
        if not self.connected or not self.sftp or self.busy:
            return

        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.tree.focus(row_id)
        else:
            self.tree.selection_remove(*self.tree.selection())

        self.show_file_context_menu(event.x_root, event.y_root)

    def show_file_context_menu(self, x_root, y_root):
        item = self.selected_remote_item()
        menu = self.file_context_menu
        menu.delete(0, "end")

        if item:
            if item["is_dir"]:
                menu.add_command(label="Apri", command=lambda p=item["path"]: self.open_folder(p))
                menu.add_command(label="Apri terminale qui", command=lambda p=item["path"]: self.open_remote_terminal(p))
                menu.add_separator()
            else:
                if self.is_image_file(item["name"]):
                    menu.add_command(label="Anteprima", command=lambda current=item: self.preview_remote_image(current))
                elif self.is_text_file(item["name"]):
                    menu.add_command(label="Apri / modifica", command=lambda current=item: self.edit_remote_text_file(current))
                menu.add_command(label="Scarica su PC2...", command=self.download_selected_file)
                menu.add_separator()
            menu.add_command(label="Rinomina", command=self.rename_selected_item)
            menu.add_command(label="Copia", command=lambda: self.set_remote_clipboard("copy"))
            menu.add_command(label="Taglia", command=lambda: self.set_remote_clipboard("move"))
            menu.add_command(label="Copia in...", command=lambda: self.copy_or_move_selected("copy"))
            menu.add_command(label="Sposta in...", command=lambda: self.copy_or_move_selected("move"))
            menu.add_separator()
            menu.add_command(label="Elimina", command=self.delete_selected_item)
            menu.add_separator()

        paste_state = "normal" if self.remote_clipboard else "disabled"
        menu.add_command(label="Incolla qui", command=self.paste_remote_item, state=paste_state)
        menu.add_command(label="Nuova cartella", command=self.create_remote_folder)
        menu.add_command(label="Terminale nella cartella corrente", command=lambda: self.open_remote_terminal(self.current_remote_path))
        menu.add_command(label="Aggiorna", command=self.refresh_folder)

        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def validate_remote_name(self, name):
        name = (name or "").strip()
        if not name or name in (".", ".."):
            raise ValueError("Il nome non può essere vuoto.")
        if re.search(r'[<>:"/\\|?*]', name) or name.endswith((" ", ".")):
            raise ValueError('Il nome contiene caratteri non validi per Windows: < > : " / \\ | ? *')
        stem = name.split(".", 1)[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9]", stem):
            raise ValueError("Il nome scelto è riservato da Windows.")
        return name

    def ps_literal(self, value):
        return "'" + str(value).replace("'", "''") + "'"

    def powershell_encoded_command(self, script):
        preamble = (
            "$ErrorActionPreference = 'Stop'; "
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
            "$OutputEncoding = [Console]::OutputEncoding; "
        )
        encoded = base64.b64encode((preamble + script).encode("utf-16le")).decode("ascii")
        return f"powershell.exe -NoLogo -NoProfile -NonInteractive -EncodedCommand {encoded}"

    def start_remote_file_operation(self, title, script, refresh_path=None, clear_clipboard=False):
        if not self.ensure_connected():
            return
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._remote_file_operation_thread,
            args=(title, script, refresh_path or self.current_remote_path, clear_clipboard),
            daemon=True,
        ).start()

    def _remote_file_operation_thread(self, title, script, refresh_path, clear_clipboard):
        try:
            self.enqueue("output", f"\n=== {title} ===")
            command = self.powershell_encoded_command(script)
            code, out, err = self.run_command_quiet(command, timeout=None)
            details = "\n".join(part.strip() for part in (out, err) if part.strip())
            if code != 0:
                raise RuntimeError(details or f"Il comando remoto è terminato con codice {code}.")
            if details:
                self.enqueue("output", details)
            self.enqueue("output", f"{title}: operazione completata.")
            if clear_clipboard:
                self.remote_clipboard = None
            self.open_folder(refresh_path)
        except Exception as e:
            self.enqueue("output", f"{title}: operazione fallita: {e}")
            self.enqueue("error_dialog", f"Errore - {title}", str(e))
        finally:
            self.enqueue("busy", False)

    def rename_selected_item(self):
        item = self.selected_remote_item()
        if not item:
            return
        new_name = simpledialog.askstring(
            "Rinomina",
            f"Nuovo nome per:\n{item['name']}",
            initialvalue=item["name"],
            parent=self.root,
        )
        if new_name is None:
            return
        try:
            new_name = self.validate_remote_name(new_name)
        except ValueError as e:
            messagebox.showwarning("Nome non valido", str(e), parent=self.root)
            return
        if new_name == item["name"]:
            return
        script = (
            f"Rename-Item -LiteralPath {self.ps_literal(self.sftp_to_windows_path(item['path']))} "
            f"-NewName {self.ps_literal(new_name)}"
        )
        self.start_remote_file_operation("Rinomina", script)

    def set_remote_clipboard(self, action):
        item = self.selected_remote_item()
        if not item:
            return
        self.remote_clipboard = {
            "action": action,
            "path": item["path"],
            "name": item["name"],
            "is_dir": item["is_dir"],
        }
        verb = "Copiato" if action == "copy" else "Tagliato"
        self.append_output(f"{verb} negli appunti remoti: {item['path']}")

    def paste_remote_item(self):
        clip = self.remote_clipboard
        if not clip:
            return
        source = clip["path"]
        target = posixpath.join(self.current_remote_path.rstrip("/"), clip["name"])
        source_cmp = self.normalize_sftp_path(source).lower()
        target_cmp = self.normalize_sftp_path(target).lower()
        if source_cmp == target_cmp:
            messagebox.showwarning(
                "Destinazione non valida",
                "Origine e destinazione coincidono.",
                parent=self.root,
            )
            return
        if clip["is_dir"] and target_cmp.startswith(source_cmp.rstrip("/") + "/"):
            messagebox.showwarning(
                "Destinazione non valida",
                "Una cartella non può essere copiata o spostata al proprio interno.",
                parent=self.root,
            )
            return

        source_win = self.sftp_to_windows_path(source)
        target_win = self.sftp_to_windows_path(target)
        check = (
            f"if (Test-Path -LiteralPath {self.ps_literal(target_win)}) "
            "{ throw 'Nella destinazione esiste già un elemento con lo stesso nome.' }; "
        )
        if clip["action"] == "copy":
            script = check + (
                f"Copy-Item -LiteralPath {self.ps_literal(source_win)} "
                f"-Destination {self.ps_literal(target_win)} -Recurse -Force"
            )
            self.start_remote_file_operation("Copia", script)
        else:
            script = check + (
                f"Move-Item -LiteralPath {self.ps_literal(source_win)} "
                f"-Destination {self.ps_literal(target_win)}"
            )
            self.start_remote_file_operation("Sposta", script, clear_clipboard=True)

    def copy_or_move_selected(self, action):
        item = self.selected_remote_item()
        if not item:
            return
        destination = simpledialog.askstring(
            "Copia in..." if action == "copy" else "Sposta in...",
            "Cartella remota di destinazione:",
            initialvalue=self.current_remote_path,
            parent=self.root,
        )
        if not destination:
            return
        destination = self.normalize_sftp_path(destination)
        target = posixpath.join(destination.rstrip("/"), item["name"])
        source_cmp = self.normalize_sftp_path(item["path"]).lower()
        target_cmp = self.normalize_sftp_path(target).lower()
        if source_cmp == target_cmp:
            messagebox.showwarning(
                "Destinazione non valida",
                "Origine e destinazione coincidono.",
                parent=self.root,
            )
            return
        if item["is_dir"] and target_cmp.startswith(source_cmp.rstrip("/") + "/"):
            messagebox.showwarning(
                "Destinazione non valida",
                "Una cartella non può essere copiata o spostata al proprio interno.",
                parent=self.root,
            )
            return

        source_win = self.sftp_to_windows_path(item["path"])
        target_win = self.sftp_to_windows_path(target)
        check = (
            f"if (-not (Test-Path -LiteralPath {self.ps_literal(self.sftp_to_windows_path(destination))} "
            "-PathType Container)) { throw 'La cartella di destinazione non esiste.' }; "
            f"if (Test-Path -LiteralPath {self.ps_literal(target_win)}) "
            "{ throw 'Nella destinazione esiste già un elemento con lo stesso nome.' }; "
        )
        if action == "copy":
            script = check + (
                f"Copy-Item -LiteralPath {self.ps_literal(source_win)} "
                f"-Destination {self.ps_literal(target_win)} -Recurse -Force"
            )
            self.start_remote_file_operation("Copia", script)
        else:
            script = check + (
                f"Move-Item -LiteralPath {self.ps_literal(source_win)} "
                f"-Destination {self.ps_literal(target_win)}"
            )
            self.start_remote_file_operation("Sposta", script)

    def delete_selected_item(self):
        item = self.selected_remote_item()
        if not item:
            return
        kind = "la cartella e tutto il suo contenuto" if item["is_dir"] else "il file"
        if not messagebox.askyesno(
            "Conferma eliminazione",
            f"Eliminare definitivamente {kind}?\n\n{item['path']}",
            icon="warning",
            parent=self.root,
        ):
            return
        script = f"Remove-Item -LiteralPath {self.ps_literal(self.sftp_to_windows_path(item['path']))} -Recurse -Force"
        self.start_remote_file_operation("Elimina", script)

    def create_remote_folder(self):
        name = simpledialog.askstring(
            "Nuova cartella",
            "Nome della nuova cartella:",
            parent=self.root,
        )
        if name is None:
            return
        try:
            name = self.validate_remote_name(name)
        except ValueError as e:
            messagebox.showwarning("Nome non valido", str(e), parent=self.root)
            return
        path = posixpath.join(self.current_remote_path.rstrip("/"), name)
        path_win = self.sftp_to_windows_path(path)
        script = (
            f"if (Test-Path -LiteralPath {self.ps_literal(path_win)}) "
            "{ throw 'Esiste già un elemento con questo nome.' }; "
            f"New-Item -ItemType Directory -Path {self.ps_literal(path_win)} | Out-Null"
        )
        self.start_remote_file_operation("Nuova cartella", script)

    def download_selected_file(self):
        item = self.selected_remote_item()
        if not item or item["is_dir"] or not self.ensure_connected():
            return
        suffix = Path(item["name"]).suffix
        local_path = filedialog.asksaveasfilename(
            title="Scarica file da PC1",
            initialfile=item["name"],
            defaultextension=suffix,
            filetypes=[("Tutti i file", "*.*")],
            parent=self.root,
        )
        if not local_path:
            return
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._download_to_pc2_thread,
            args=(item, local_path),
            daemon=True,
        ).start()

    def _download_to_pc2_thread(self, item, local_path):
        download_sftp = None
        partial_path = Path(str(local_path) + ".part")
        try:
            download_sftp = self.client.open_sftp()
            total = int(item.get("raw_size") or download_sftp.stat(item["path"]).st_size)
            transferred = 0
            chunk_size = 8 * 1024 * 1024
            start_time = time.time()
            last_report_time = 0.0
            last_report_percent = -1

            self.enqueue("output", f"Download SFTP:\n{item['path']}\n→ {local_path}")
            self.enqueue("upload_progress", 0.0, "Download su PC2: 0%")

            with download_sftp.open(item["path"], "rb") as remote_file:
                with open(partial_path, "wb") as local_file:
                    while True:
                        chunk = remote_file.read(chunk_size)
                        if not chunk:
                            break
                        local_file.write(chunk)
                        transferred += len(chunk)

                        percent = (transferred / total * 100.0) if total else 0.0
                        rounded_percent = int(percent)
                        now = time.time()
                        if rounded_percent != last_report_percent or now - last_report_time >= 1.0:
                            elapsed = max(now - start_time, 0.1)
                            speed = transferred / elapsed
                            remaining = max(total - transferred, 0)
                            eta = self.format_seconds(remaining / speed) if speed > 0 else "—"
                            text = (
                                f"Download su PC2: {percent:.1f}%  "
                                f"{self.format_size(transferred)} / {self.format_size(total)}  "
                                f"{self.format_size(speed)}/s  ETA {eta}"
                            )
                            self.enqueue("upload_progress", percent, text)
                            last_report_time = now
                            last_report_percent = rounded_percent

            os.replace(partial_path, local_path)
            self.enqueue("upload_progress", 100.0, "Download su PC2 completato")
            self.enqueue("output", f"Download completato: {local_path}")
            self.enqueue("info_dialog", "Download completato", f"File salvato su PC2:\n{local_path}")
        except Exception as e:
            try:
                if partial_path.exists():
                    partial_path.unlink()
            except Exception:
                pass
            self.enqueue("upload_progress", 0.0, "Download su PC2 fallito")
            self.enqueue("error_dialog", "Errore download su PC2", str(e))
        finally:
            if download_sftp:
                try:
                    download_sftp.close()
                except Exception:
                    pass
            self.enqueue("busy", False)

    def preview_remote_image(self, item):
        if Image is None or ImageTk is None:
            messagebox.showerror(
                "Anteprima non disponibile",
                "Per visualizzare le anteprime installa Pillow con: py -m pip install pillow",
                parent=self.root,
            )
            return
        if not self.ensure_connected():
            return

        window = tk.Toplevel(self.root)
        window.title(f"Anteprima - {item['name']}")
        window.geometry("800x650")
        window.minsize(420, 320)
        window.configure(bg=BG)
        label = tk.Label(
            window,
            text="Caricamento anteprima da PC1...",
            bg=PANEL_2,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        label.pack(fill="both", expand=True, padx=10, pady=10)
        preview = {"window": window, "label": label, "name": item["name"]}
        threading.Thread(
            target=self._preview_remote_image_thread,
            args=(preview, item["path"]),
            daemon=True,
        ).start()

    def _preview_remote_image_thread(self, preview, remote_path):
        preview_sftp = None
        try:
            preview_sftp = self.client.open_sftp()
            file_size = preview_sftp.stat(remote_path).st_size
            if file_size > THUMBNAIL_MAX_FILE_SIZE * 4:
                raise RuntimeError("Il file è troppo grande per l'anteprima diretta.")
            with preview_sftp.open(remote_path, "rb") as remote_file:
                data = remote_file.read()
            image = Image.open(BytesIO(data))
            image = ImageOps.exif_transpose(image)
            image.load()
            self.enqueue("preview_image", preview, image.convert("RGBA"))
        except Exception as e:
            self.enqueue("preview_error", preview, str(e))
        finally:
            if preview_sftp:
                try:
                    preview_sftp.close()
                except Exception:
                    pass

    def apply_preview_image(self, preview, image):
        window = preview["window"]
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return

        max_width = min(1400, max(self.root.winfo_screenwidth() - 120, 420))
        max_height = min(900, max(self.root.winfo_screenheight() - 180, 320))
        image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)
        label = preview["label"]
        label.configure(image=photo, text="", bg="#080f1d")
        label.image = photo
        window.geometry(f"{max(image.width + 20, 420)}x{max(image.height + 20, 320)}")

    def show_preview_error(self, preview, error):
        window = preview["window"]
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return
        preview["label"].configure(
            text=f"Impossibile visualizzare l'immagine.\n\n{error}",
            fg="#f85149",
        )

    def edit_remote_text_file(self, item):
        if not self.ensure_connected():
            return
        if item.get("raw_size", 0) > REMOTE_TEXT_MAX_FILE_SIZE:
            messagebox.showwarning(
                "File troppo grande",
                "L'editor remoto apre file di testo fino a 5 MB. Puoi comunque scaricarlo su PC2.",
            )
            return

        editor = {
            "window": tk.Toplevel(self.root),
            "item": dict(item),
            "dirty": False,
            "encoding": "utf-8",
            "loading": True,
        }
        window = editor["window"]
        window.title(f"Editor remoto PC1 - {item['name']}")
        window.geometry("1000x680")
        window.minsize(700, 450)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", lambda: self.close_remote_text_editor(editor))

        toolbar = tk.Frame(window, bg=PANEL)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text=item["path"], bg=PANEL, fg=MUTED, anchor="w",
                 font=("Consolas", 9)).pack(side="left", fill="x", expand=True, padx=10, pady=9)
        save_button = self.make_button(
            toolbar,
            "Salva su PC1",
            lambda: self.save_remote_text(editor),
            GREEN,
            GREEN_HOVER,
            width=12,
        )
        save_button.pack(side="right", padx=(4, 8), pady=5)
        editor["save_button"] = save_button
        reload_button = self.make_button(
            toolbar,
            "Ricarica",
            lambda: self.reload_remote_text(editor),
            "#303a49",
            "#3b4658",
            width=8,
        )
        reload_button.pack(side="right", padx=4, pady=5)
        editor["reload_button"] = reload_button

        text_frame = tk.Frame(window, bg=BG)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        text_widget = tk.Text(
            text_frame,
            bg="#080f1d",
            fg="#d6e2f0",
            insertbackground=TEXT,
            selectbackground="#243b61",
            relief="flat",
            wrap="none",
            undo=True,
            font=("Consolas", 10),
        )
        text_widget.pack(side="left", fill="both", expand=True)
        vertical = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        vertical.pack(side="right", fill="y")
        horizontal = ttk.Scrollbar(window, orient="horizontal", command=text_widget.xview)
        horizontal.pack(fill="x", padx=10)
        text_widget.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set, state="disabled")
        editor["text"] = text_widget

        status_var = StringVar(value="Caricamento dal PC1...")
        editor["status_var"] = status_var
        tk.Label(window, textvariable=status_var, bg=BG, fg=MUTED, anchor="w",
                 font=("Segoe UI", 8)).pack(fill="x", padx=10, pady=(4, 8))

        self.set_button_enabled(save_button, False)
        threading.Thread(target=self._load_remote_text_thread, args=(editor,), daemon=True).start()

    def _load_remote_text_thread(self, editor):
        editor_sftp = None
        try:
            editor_sftp = self.client.open_sftp()
            with editor_sftp.open(editor["item"]["path"], "rb") as remote_file:
                data = remote_file.read(REMOTE_TEXT_MAX_FILE_SIZE + 1)
            if len(data) > REMOTE_TEXT_MAX_FILE_SIZE:
                raise ValueError("Il file supera il limite di 5 MB dell'editor remoto.")
            if data.startswith(b"\xef\xbb\xbf"):
                content = data.decode("utf-8-sig")
                encoding = "utf-8-sig"
            else:
                try:
                    content = data.decode("utf-8")
                    encoding = "utf-8"
                except UnicodeDecodeError:
                    content = data.decode("cp1252")
                    encoding = "cp1252"
            self.enqueue("editor_loaded", editor, content, encoding)
        except Exception as error:
            self.enqueue("editor_error", editor, error)
        finally:
            if editor_sftp:
                try:
                    editor_sftp.close()
                except Exception:
                    pass

    def apply_remote_text(self, editor, content, encoding):
        window = editor.get("window")
        if not window or not window.winfo_exists():
            return
        text_widget = editor["text"]
        text_widget.configure(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", content)
        text_widget.edit_reset()
        text_widget.edit_modified(False)
        text_widget.bind("<<Modified>>", lambda _event: self.mark_remote_text_modified(editor))
        editor["encoding"] = encoding
        editor["dirty"] = False
        editor["loading"] = False
        editor["status_var"].set(f"Caricato da PC1 · {encoding} · {len(content):,} caratteri")
        self.set_button_enabled(editor["save_button"], True)
        text_widget.focus_set()

    def mark_remote_text_modified(self, editor):
        text_widget = editor.get("text")
        if not text_widget or not text_widget.edit_modified():
            return
        text_widget.edit_modified(False)
        if editor.get("loading"):
            return
        editor["dirty"] = True
        editor["status_var"].set("Modifiche non salvate")

    def save_remote_text(self, editor):
        if editor.get("loading") or not self.ensure_connected():
            return
        content = editor["text"].get("1.0", "end-1c")
        editor["status_var"].set("Salvataggio su PC1...")
        self.set_button_enabled(editor["save_button"], False)
        threading.Thread(
            target=self._save_remote_text_thread,
            args=(editor, content, editor["encoding"]),
            daemon=True,
        ).start()

    def _save_remote_text_thread(self, editor, content, encoding):
        editor_sftp = None
        try:
            editor_sftp = self.client.open_sftp()
            encoded = content.encode(encoding)
            with editor_sftp.open(editor["item"]["path"], "wb") as remote_file:
                remote_file.write(encoded)
            self.enqueue("editor_saved", editor)
        except Exception as error:
            self.enqueue("editor_error", editor, error)
        finally:
            if editor_sftp:
                try:
                    editor_sftp.close()
                except Exception:
                    pass

    def finish_remote_text_save(self, editor):
        window = editor.get("window")
        if not window or not window.winfo_exists():
            return
        editor["dirty"] = False
        editor["status_var"].set(f"Salvato su PC1 · {time.strftime('%H:%M:%S')}")
        self.set_button_enabled(editor["save_button"], True)
        self.refresh_folder()

    def show_remote_editor_error(self, editor, error):
        window = editor.get("window")
        if not window or not window.winfo_exists():
            return
        editor["loading"] = False
        editor["status_var"].set(f"Errore: {error}")
        self.set_button_enabled(editor["save_button"], self.ensure_connected())
        messagebox.showerror("Editor remoto", str(error), parent=window)

    def reload_remote_text(self, editor):
        if editor.get("dirty") and not messagebox.askyesno(
            "Scartare modifiche?",
            "Ricaricando il file perderai le modifiche non salvate. Continuare?",
            parent=editor["window"],
        ):
            return
        editor["loading"] = True
        editor["status_var"].set("Ricaricamento dal PC1...")
        self.set_button_enabled(editor["save_button"], False)
        threading.Thread(target=self._load_remote_text_thread, args=(editor,), daemon=True).start()

    def close_remote_text_editor(self, editor):
        if editor.get("dirty") and not messagebox.askyesno(
            "Modifiche non salvate",
            "Chiudere l'editor e perdere le modifiche non salvate?",
            parent=editor["window"],
        ):
            return
        editor["window"].destroy()

    def open_remote_terminal(self, remote_path):
        if not self.ensure_connected():
            return
        remote_path = self.normalize_sftp_path(remote_path)
        terminal = {
            "window": tk.Toplevel(self.root),
            "path": remote_path,
            "channel": None,
            "closed": False,
        }
        self.terminal_sessions.append(terminal)
        window = terminal["window"]
        window.title(f"SSH pc-lavoro - {remote_path}")
        window.geometry("900x560")
        window.minsize(650, 400)
        window.configure(bg=BG)
        window.protocol("WM_DELETE_WINDOW", lambda: self.close_remote_terminal(terminal))

        tk.Label(
            window,
            text=f"PowerShell SSH persistente · {self.user_var.get()}@{self.host_var.get()} · {remote_path}",
            bg=BG,
            fg=TEXT,
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x", padx=12, pady=(12, 6))

        output = tk.Text(
            window,
            bg="#080f1d",
            fg="#c9d7ea",
            insertbackground=TEXT,
            relief="flat",
            wrap="word",
            font=("Consolas", 10),
        )
        output.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        terminal["output"] = output
        output.insert(
            "end",
            "Apertura della sessione SSH interattiva...\n"
            "La cartella e lo stato di PowerShell restano attivi tra un comando e l'altro.\n\n",
        )
        output.configure(state="disabled")

        command_row = tk.Frame(window, bg=BG)
        command_row.pack(fill="x", padx=12, pady=(0, 12))
        tk.Label(command_row, text=">", bg=BG, fg="#58a6ff", font=("Consolas", 11, "bold")).pack(side="left")
        entry = tk.Entry(
            command_row,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Consolas", 10),
        )
        entry.pack(side="left", fill="x", expand=True, padx=(8, 8), ipady=8)
        terminal["entry"] = entry
        run_button = self.make_button(
            command_row,
            "Esegui",
            lambda: self.run_terminal_command(terminal),
            GREEN,
            GREEN_HOVER,
            width=10,
        )
        run_button.pack(side="right")
        terminal["run_button"] = run_button
        entry.bind("<Return>", lambda _event: self.run_terminal_command(terminal))
        interrupt_button = self.make_button(
            command_row,
            "Ctrl+C",
            lambda: self.interrupt_remote_terminal(terminal),
            RED,
            RED_HOVER,
            width=7,
        )
        interrupt_button.pack(side="right", padx=(0, 6))
        terminal["interrupt_button"] = interrupt_button
        entry.focus_set()

        try:
            channel = self.client.invoke_shell(term="xterm", width=140, height=40)
            terminal["channel"] = channel
            path_win = self.sftp_to_windows_path(remote_path)
            channel.send("powershell.exe -NoLogo -NoProfile\r\n")
            channel.send(f"Set-Location -LiteralPath {self.ps_literal(path_win)}\r\n")
            threading.Thread(target=self._terminal_reader_thread, args=(terminal,), daemon=True).start()
        except Exception as error:
            self.append_terminal_output(terminal, f"Impossibile aprire il terminale SSH: {error}\n")
            self.set_button_enabled(run_button, False)
            self.set_button_enabled(interrupt_button, False)

    def run_terminal_command(self, terminal):
        if terminal.get("closed") or not self.ensure_connected():
            return
        entry = terminal["entry"]
        command_text = entry.get()
        if not command_text:
            return
        entry.delete(0, "end")
        try:
            terminal["channel"].send(command_text + "\r\n")
        except Exception as error:
            self.append_terminal_output(terminal, f"\n[Errore invio comando: {error}]\n")

    def _terminal_reader_thread(self, terminal):
        channel = terminal.get("channel")
        try:
            while channel and not terminal.get("closed"):
                if channel.recv_ready():
                    data = channel.recv(8192).decode("utf-8", errors="replace")
                    if data:
                        data = ANSI_ESCAPE_RE.sub("", data).replace("\r\r\n", "\n").replace("\r\n", "\n")
                        self.enqueue("terminal_output", terminal, data)
                elif channel.closed or channel.exit_status_ready():
                    break
                else:
                    time.sleep(0.05)
        except Exception as error:
            if not terminal.get("closed"):
                self.enqueue("terminal_output", terminal, f"\n[Sessione SSH interrotta: {error}]\n")
        finally:
            self.enqueue("terminal_done", terminal)

    def interrupt_remote_terminal(self, terminal):
        channel = terminal.get("channel")
        if channel and not channel.closed:
            try:
                channel.send("\x03")
            except Exception:
                pass

    def close_remote_terminal(self, terminal):
        terminal["closed"] = True
        channel = terminal.get("channel")
        if channel:
            try:
                channel.close()
            except Exception:
                pass
        if terminal in self.terminal_sessions:
            self.terminal_sessions.remove(terminal)
        window = terminal.get("window")
        try:
            if window and window.winfo_exists():
                window.destroy()
        except Exception:
            pass

    def append_terminal_output(self, terminal, text):
        window = terminal.get("window")
        if not window or not window.winfo_exists():
            return
        output = terminal["output"]
        output.configure(state="normal")
        output.insert("end", text)
        output.see("end")
        output.configure(state="disabled")

    def finish_terminal_command(self, terminal):
        window = terminal.get("window")
        if not window or not window.winfo_exists():
            return
        self.append_terminal_output(terminal, "\n[Sessione SSH chiusa]\n")
        self.set_button_enabled(terminal["run_button"], False)
        self.set_button_enabled(terminal["interrupt_button"], False)

    def sftp_to_windows_path(self, path):
        path = self.normalize_sftp_path(path)
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return path.replace("/", "\\")

    def ensure_remote_download_helper(self):
        helper_code = 'import json\nimport os\nimport re\nimport sys\nimport time\nimport urllib.parse\nimport urllib.request\nfrom pathlib import Path\nfrom email.message import Message\n\nCONFIG_PATH = r"C:\\Users\\tesi\\Desktop\\comfy_remote_download_config.json"\nCHUNK_SIZE = 8 * 1024 * 1024\n\n\ndef fmt_size(num):\n    num = float(num)\n    for unit in ["B", "KB", "MB", "GB", "TB"]:\n        if num < 1024:\n            if unit == "B":\n                return f"{num:.0f} {unit}"\n            return f"{num:.2f} {unit}"\n        num /= 1024\n    return f"{num:.2f} PB"\n\n\ndef fmt_time(seconds):\n    seconds = max(int(seconds), 0)\n    h, rem = divmod(seconds, 3600)\n    m, s = divmod(rem, 60)\n    if h:\n        return f"{h}h {m}m"\n    if m:\n        return f"{m}m {s}s"\n    return f"{s}s"\n\n\ndef sanitize_filename(name):\n    name = urllib.parse.unquote(name or "").strip().strip(\'"\')\n    name = re.sub(r\'[<>:"/\\\\|?*]+\', "_", name)\n    name = name.rstrip(" .")\n    return name or "downloaded_model"\n\n\ndef filename_from_content_disposition(value):\n    if not value:\n        return None\n    msg = Message()\n    msg["content-disposition"] = value\n    params = msg.get_params(header="content-disposition", failobj=[])\n    for key, val in params:\n        if key.lower() == "filename*":\n            try:\n                parts = str(val).split("\'", 2)\n                if len(parts) == 3:\n                    return urllib.parse.unquote(parts[2])\n            except Exception:\n                pass\n        if key.lower() == "filename":\n            return val\n    return None\n\n\ndef filename_from_url(url):\n    parsed = urllib.parse.urlparse(url)\n    name = os.path.basename(parsed.path)\n    return name or None\n\n\ndef main():\n    with open(CONFIG_PATH, "r", encoding="utf-8") as f:\n        cfg = json.load(f)\n\n    url = cfg["url"].strip()\n    dest_dir = Path(cfg["dest_dir"])\n    forced_filename = (cfg.get("filename") or "").strip()\n    token = (cfg.get("token") or "").strip()\n\n    dest_dir.mkdir(parents=True, exist_ok=True)\n\n    headers = {"User-Agent": "Mozilla/5.0 comfy-remote-downloader"}\n    if token:\n        headers["Authorization"] = f"Bearer {token}"\n\n    request = urllib.request.Request(url, headers=headers)\n    response = urllib.request.urlopen(request, timeout=60)\n\n    cd_name = filename_from_content_disposition(response.headers.get("Content-Disposition"))\n    url_name = filename_from_url(response.geturl()) or filename_from_url(url)\n    filename = sanitize_filename(forced_filename or cd_name or url_name or "downloaded_model")\n    dest_path = dest_dir / filename\n\n    content_length = response.headers.get("Content-Length")\n    total_size = int(content_length) if content_length and content_length.isdigit() else 0\n    response.close()\n\n    existing_size = dest_path.stat().st_size if dest_path.exists() else 0\n    resume = existing_size > 0 and total_size > 0 and existing_size < total_size\n\n    headers2 = dict(headers)\n    if resume:\n        headers2["Range"] = f"bytes={existing_size}-"\n        print(f"Riprendo download da {fmt_size(existing_size)}", flush=True)\n    elif dest_path.exists() and total_size and existing_size >= total_size:\n        print(f"File già presente e completo: {dest_path}", flush=True)\n        print("REMOTE_DOWNLOAD_DONE", flush=True)\n        return\n    elif dest_path.exists():\n        print("File esistente: sovrascrivo da zero.", flush=True)\n        existing_size = 0\n\n    print(f"Destinazione: {dest_path}", flush=True)\n    print(f"URL finale: {url}", flush=True)\n    if total_size:\n        print(f"Dimensione stimata: {fmt_size(total_size)}", flush=True)\n    else:\n        print("Dimensione non dichiarata dal server.", flush=True)\n\n    request2 = urllib.request.Request(url, headers=headers2)\n    response2 = urllib.request.urlopen(request2, timeout=60)\n\n    status = getattr(response2, "status", None)\n    if resume and status != 206:\n        print("Il server non supporta resume per questo link: riparto da zero.", flush=True)\n        existing_size = 0\n        mode = "wb"\n    else:\n        mode = "ab" if resume else "wb"\n\n    if not total_size:\n        length2 = response2.headers.get("Content-Length")\n        if length2 and length2.isdigit():\n            total_size = int(length2) + existing_size\n\n    downloaded = existing_size\n    start = time.time()\n    last_report = 0\n    last_percent_int = -1\n\n    with open(dest_path, mode) as out:\n        while True:\n            chunk = response2.read(CHUNK_SIZE)\n            if not chunk:\n                break\n            out.write(chunk)\n            downloaded += len(chunk)\n\n            now = time.time()\n            percent = (downloaded / total_size * 100.0) if total_size else 0.0\n            percent_int = int(percent) if total_size else -1\n\n            if now - last_report >= 2.0 or percent_int != last_percent_int:\n                elapsed = max(now - start, 0.1)\n                speed = max((downloaded - existing_size) / elapsed, 1)\n                if total_size:\n                    remaining = max(total_size - downloaded, 0)\n                    eta = fmt_time(remaining / speed)\n                    print(f"DOWNLOAD_PROGRESS {percent:.1f}%  {fmt_size(downloaded)} / {fmt_size(total_size)}  {fmt_size(speed)}/s  ETA {eta}", flush=True)\n                else:\n                    print(f"DOWNLOAD_PROGRESS {fmt_size(downloaded)}  {fmt_size(speed)}/s", flush=True)\n                last_report = now\n                last_percent_int = percent_int\n\n    response2.close()\n    print(f"Download completato: {dest_path}", flush=True)\n    print("REMOTE_DOWNLOAD_DONE", flush=True)\n\n\nif __name__ == "__main__":\n    try:\n        main()\n    except Exception as e:\n        print(f"REMOTE_DOWNLOAD_ERROR: {e}", flush=True)\n        sys.exit(1)\n'
        with self.sftp.open(REMOTE_DOWNLOAD_HELPER_SFTP, "w") as f:
            f.write(helper_code)

    def download_url_here(self):
        if not self.connected or not self.sftp:
            return

        url = simpledialog.askstring(
            "Scarica modello da URL",
            "Incolla il link diretto di download.\nIl download partirà direttamente da PC1 nella cartella remota attuale.",
            parent=self.root,
        )
        if not url:
            return
        url = url.strip()

        filename = simpledialog.askstring(
            "Nome file opzionale",
            "Nome file da salvare su PC1.\nLascia vuoto per usare il nome proposto dal server/link.",
            parent=self.root,
        )
        filename = (filename or "").strip()

        token = simpledialog.askstring(
            "Token opzionale",
            "Token Bearer opzionale, utile per modelli privati/gated.\nLascia vuoto per download pubblici.",
            parent=self.root,
            show="*",
        )
        token = (token or "").strip()

        dest_dir_win = self.sftp_to_windows_path(self.current_remote_path)
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._download_url_thread,
            args=(url, dest_dir_win, filename, token),
            daemon=True,
        ).start()

    def _download_url_thread(self, url, dest_dir_win, filename, token):
        try:
            self.enqueue("output", f"Download diretto su PC1:\n{url}\n→ {dest_dir_win}")
            self.enqueue("upload_progress", 0.0, "Download remoto: preparazione...")
            self.ensure_remote_download_helper()

            cfg = {
                "url": url,
                "dest_dir": dest_dir_win,
                "filename": filename,
                "token": token,
            }
            with self.sftp.open(REMOTE_DOWNLOAD_CONFIG_SFTP, "w") as f:
                f.write(json.dumps(cfg, ensure_ascii=False, indent=2))

            command = f'py "{REMOTE_DOWNLOAD_HELPER_WIN}"'
            code, out, err = self.run_command(command, title="DOWNLOAD DIRETTO SU PC1", stream=True, timeout=None)

            if code == 0:
                self.enqueue("upload_progress", 100.0, "Download remoto completato")
                self.enqueue("output", "Download remoto completato.")
                self.open_folder(self.current_remote_path)
            else:
                self.enqueue("upload_progress", 0.0, "Download remoto fallito")
                self.enqueue("output", f"Download remoto fallito. Exit code: {code}")
        except Exception as e:
            self.enqueue("upload_progress", 0.0, "Download remoto fallito")
            self.enqueue("error_dialog", "Errore download remoto", str(e))
        finally:
            self.enqueue("busy", False)

    def show_upload_menu(self):
        if not self.connected or not self.sftp or self.busy:
            return
        try:
            x = self.btn_upload.winfo_rootx()
            y = self.btn_upload.winfo_rooty() + self.btn_upload.winfo_height()
            self.upload_menu.tk_popup(x, y)
        finally:
            self.upload_menu.grab_release()

    def upload_file(self):
        if not self.connected or not self.sftp:
            return
        local_path = filedialog.askopenfilename(title="Scegli file da caricare su PC1", parent=self.root)
        if not local_path:
            return
        remote_path = self.current_remote_path.rstrip("/") + "/" + Path(local_path).name
        replace_existing = self.confirm_upload_replace(remote_path, uploading_folder=False)
        if replace_existing is None:
            return
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._upload_file_thread,
            args=(local_path, remote_path, replace_existing),
            daemon=True,
        ).start()

    def upload_folder(self):
        if not self.connected or not self.sftp:
            return
        local_path = filedialog.askdirectory(title="Scegli cartella da caricare su PC1", parent=self.root)
        if not local_path:
            return
        folder_name = Path(local_path).name or "cartella"
        remote_path = self.current_remote_path.rstrip("/") + "/" + folder_name
        replace_existing = self.confirm_upload_replace(remote_path, uploading_folder=True)
        if replace_existing is None:
            return
        self.busy = True
        self.update_buttons()
        threading.Thread(
            target=self._upload_folder_thread,
            args=(local_path, remote_path, replace_existing),
            daemon=True,
        ).start()

    def is_sftp_not_found(self, error):
        if isinstance(error, FileNotFoundError):
            return True
        err_no = getattr(error, "errno", None)
        if err_no == errno.ENOENT:
            return True
        text = str(error).lower()
        return "no such file" in text or "not found" in text or "impossibile trovare" in text

    def remote_item_info(self, sftp, remote_path):
        try:
            attr = sftp.stat(remote_path)
            return {
                "exists": True,
                "is_dir": self.is_dir_attr(attr),
                "size": getattr(attr, "st_size", 0),
            }
        except OSError as e:
            if self.is_sftp_not_found(e):
                return None
            raise

    def confirm_upload_replace(self, remote_path, uploading_folder):
        try:
            info = self.remote_item_info(self.sftp, remote_path)
        except Exception as e:
            messagebox.showerror(
                "Controllo destinazione fallito",
                f"Non riesco a controllare se esiste già un elemento con lo stesso nome su PC1:\n\n{remote_path}\n\n{e}",
                parent=self.root,
            )
            return None

        if not info:
            return False

        upload_kind = "cartella" if uploading_folder else "file"
        existing_kind = "cartella" if info["is_dir"] else "file"
        action = (
            "La cartella remota esistente verrà eliminata e ricaricata da zero."
            if uploading_folder
            else "Il file remoto esistente verrà sovrascritto."
        )
        if uploading_folder and not info["is_dir"]:
            action = "Il file remoto esistente verrà eliminato e sostituito dalla cartella."
        elif not uploading_folder and info["is_dir"]:
            action = "La cartella remota esistente verrà eliminata e sostituita dal file."

        if not messagebox.askyesno(
            "Elemento già presente",
            (
                f"Su PC1 esiste già un/a {existing_kind} con lo stesso nome.\n\n"
                f"Stai caricando un/a {upload_kind} in:\n{remote_path}\n\n"
                f"Vuoi sostituire?\n\n{action}"
            ),
            icon="warning",
            parent=self.root,
        ):
            self.append_output(f"Upload annullato: elemento già presente su PC1: {remote_path}")
            return None

        return True

    def remove_remote_item(self, sftp, remote_path):
        info = self.remote_item_info(sftp, remote_path)
        if not info:
            return

        if not info["is_dir"]:
            sftp.remove(remote_path)
            return

        for attr in sftp.listdir_attr(remote_path):
            name = attr.filename
            if name in (".", ".."):
                continue
            child_path = posixpath.join(remote_path.rstrip("/"), name)
            if self.is_dir_attr(attr):
                self.remove_remote_item(sftp, child_path)
            else:
                sftp.remove(child_path)
        sftp.rmdir(remote_path)

    def ensure_remote_dir(self, sftp, remote_dir):
        remote_dir = remote_dir.rstrip("/")
        if not remote_dir or remote_dir == "/":
            return

        try:
            attr = sftp.stat(remote_dir)
            if not self.is_dir_attr(attr):
                raise RuntimeError(f"Esiste gia' un file con questo nome: {remote_dir}")
            return
        except FileNotFoundError:
            pass
        except OSError as e:
            if getattr(e, "errno", None) not in (2, None):
                raise

        parent = posixpath.dirname(remote_dir)
        if parent and parent != remote_dir:
            self.ensure_remote_dir(sftp, parent)
        try:
            sftp.mkdir(remote_dir)
        except OSError:
            attr = sftp.stat(remote_dir)
            if not self.is_dir_attr(attr):
                raise

    def upload_file_chunks(self, sftp, local_path, remote_path, progress):
        chunk_size = 8 * 1024 * 1024
        total = progress["total"]

        with open(local_path, "rb") as local_file:
            with sftp.open(remote_path, "wb") as remote_file:
                while True:
                    chunk = local_file.read(chunk_size)
                    if not chunk:
                        break

                    remote_file.write(chunk)
                    progress["transferred"] += len(chunk)

                    percent = (progress["transferred"] / total * 100.0) if total else 100.0
                    now = time.time()
                    rounded_percent = int(percent)
                    percent_step = progress.get("percent_step", 1)
                    percent_changed = rounded_percent >= progress["last_report_percent"] + percent_step
                    time_elapsed = now - progress["last_report_time"] >= 2.0
                    completed = progress["transferred"] >= total

                    if percent_changed or time_elapsed or completed:
                        elapsed = max(now - progress["start_time"], 0.1)
                        speed = progress["transferred"] / elapsed
                        remaining = max(total - progress["transferred"], 0)
                        eta_seconds = int(remaining / speed) if speed > 0 else 0
                        current = progress.get("current")
                        current_text = f"  {current}" if current else ""
                        text = (
                            f"{progress['label']}: {percent:.1f}%  "
                            f"{self.format_size(float(progress['transferred']))} / {self.format_size(float(total))}  "
                            f"{self.format_size(float(speed))}/s  "
                            f"ETA {self.format_seconds(eta_seconds)}"
                            f"{current_text}"
                        )
                        self.enqueue("upload_progress", percent, text)
                        self.enqueue("output", text)
                        progress["last_report_time"] = now
                        progress["last_report_percent"] = rounded_percent

    def _upload_file_thread(self, local_path, remote_path, replace_existing=False):
        upload_sftp = None
        try:
            upload_sftp = self.client.open_sftp()
            total = Path(local_path).stat().st_size
            self.enqueue("output", f"Upload SFTP file:\n{local_path}\n-> {remote_path}")
            self.enqueue("output", f"Dimensione: {self.format_size(float(total))}")
            self.enqueue("upload_progress", 0.0, "Upload file: 0%")

            existing = self.remote_item_info(upload_sftp, remote_path)
            if existing:
                if not replace_existing:
                    raise RuntimeError(f"Su PC1 esiste gia' un elemento con questo nome: {remote_path}")
                self.enqueue("output", f"Sostituisco elemento remoto esistente: {remote_path}")
                self.remove_remote_item(upload_sftp, remote_path)

            self.ensure_remote_dir(upload_sftp, posixpath.dirname(remote_path))
            progress = {
                "label": "Upload file",
                "total": total,
                "transferred": 0,
                "start_time": time.time(),
                "last_report_time": 0.0,
                "last_report_percent": -1,
                "percent_step": 1,
                "current": Path(local_path).name,
            }
            self.upload_file_chunks(upload_sftp, local_path, remote_path, progress)

            self.enqueue("upload_progress", 100.0, "Upload file completato: 100%")
            self.enqueue("output", "Upload file completato.")
            self.open_folder(self.current_remote_path)
        except Exception as e:
            self.enqueue("upload_progress", 0.0, "Upload interrotto o fallito")
            self.enqueue("error_dialog", "Errore upload", str(e))
        finally:
            if upload_sftp:
                try:
                    upload_sftp.close()
                except Exception:
                    pass
            self.enqueue("busy", False)

    def _upload_folder_thread(self, local_path, remote_path, replace_existing=False):
        upload_sftp = None
        try:
            upload_sftp = self.client.open_sftp()
            local_root = Path(local_path)
            files = []
            dirs = []
            skipped = []
            total = 0

            for root, dirnames, filenames in os.walk(local_root):
                root_path = Path(root)
                excluded_here = [name for name in dirnames if name in UPLOAD_FOLDER_EXCLUDED_DIRS]
                if excluded_here:
                    skipped.extend(str((root_path / name).relative_to(local_root)) + "/" for name in excluded_here)
                dirnames[:] = [name for name in dirnames if name not in UPLOAD_FOLDER_EXCLUDED_DIRS]
                dirs.append(root_path)
                dirnames.sort()
                filenames.sort()
                for filename in filenames:
                    file_path = root_path / filename
                    if not file_path.is_file():
                        continue
                    rel_path = file_path.relative_to(local_root)
                    try:
                        size = file_path.stat().st_size
                    except OSError as e:
                        skipped.append(f"{rel_path.as_posix()} ({e})")
                        continue
                    files.append((file_path, rel_path, size))
                    total += size

            self.enqueue("output", f"Upload SFTP cartella:\n{local_path}\n-> {remote_path}")
            self.enqueue("output", f"Elementi: {len(files)} file, {len(dirs)} cartelle")
            self.enqueue("output", f"Dimensione totale: {self.format_size(float(total))}")
            if skipped:
                self.enqueue("output", "Saltati automaticamente:\n" + "\n".join(f"- {item}" for item in skipped[:20]))
                if len(skipped) > 20:
                    self.enqueue("output", f"...altri {len(skipped) - 20} elementi saltati.")
            self.enqueue("upload_progress", 0.0, "Upload cartella: preparazione...")

            existing = self.remote_item_info(upload_sftp, remote_path)
            if existing:
                if not replace_existing:
                    raise RuntimeError(f"Su PC1 esiste gia' un elemento con questo nome: {remote_path}")
                self.enqueue("output", f"Sostituisco elemento remoto esistente: {remote_path}")
                self.remove_remote_item(upload_sftp, remote_path)

            for local_dir in dirs:
                rel_dir = local_dir.relative_to(local_root)
                if rel_dir.parts:
                    remote_dir = posixpath.join(remote_path, *rel_dir.parts)
                else:
                    remote_dir = remote_path
                self.ensure_remote_dir(upload_sftp, remote_dir)

            if not files:
                self.enqueue("upload_progress", 100.0, "Upload cartella completato: cartella vuota")
                self.enqueue("output", "Upload cartella completato.")
                self.open_folder(self.current_remote_path)
                return

            progress = {
                "label": "Upload cartella",
                "total": total,
                "transferred": 0,
                "start_time": time.time(),
                "last_report_time": 0.0,
                "last_report_percent": -1,
                "percent_step": 1,
                "current": "",
            }

            skipped_during_upload = []
            for file_path, rel_path, _size in files:
                progress["current"] = rel_path.as_posix()
                remote_file = posixpath.join(remote_path, *rel_path.parts)
                self.ensure_remote_dir(upload_sftp, posixpath.dirname(remote_file))
                before = progress["transferred"]
                try:
                    self.upload_file_chunks(upload_sftp, file_path, remote_file, progress)
                except PermissionError as e:
                    missing = max(_size - (progress["transferred"] - before), 0)
                    progress["transferred"] += missing
                    skipped_during_upload.append(f"{rel_path.as_posix()} ({e})")
                    self.enqueue("output", f"File saltato per permessi: {rel_path.as_posix()}")
                except OSError as e:
                    missing = max(_size - (progress["transferred"] - before), 0)
                    progress["transferred"] += missing
                    skipped_during_upload.append(f"{rel_path.as_posix()} ({e})")
                    self.enqueue("output", f"File saltato: {rel_path.as_posix()} ({e})")

            self.enqueue("upload_progress", 100.0, "Upload cartella completato: 100%")
            if skipped_during_upload:
                self.enqueue("output", f"Upload cartella completato con {len(skipped_during_upload)} file saltati.")
            else:
                self.enqueue("output", "Upload cartella completato.")
            self.open_folder(self.current_remote_path)
        except Exception as e:
            self.enqueue("upload_progress", 0.0, "Upload cartella interrotto o fallito")
            self.enqueue("error_dialog", "Errore upload cartella", str(e))
        finally:
            if upload_sftp:
                try:
                    upload_sftp.close()
                except Exception:
                    pass
            self.enqueue("busy", False)

    # -----------------------------------------------------
    # LINK
    # -----------------------------------------------------
    def open_link(self):
        if self.current_link:
            webbrowser.open(self.current_link)

    def copy_link(self):
        if self.current_link:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.current_link)
            self.append_output("Link copiato negli appunti.")

    # -----------------------------------------------------
    # CLOSE
    # -----------------------------------------------------
    def on_close(self):
        self._stop_monitor = True
        for terminal in list(self.terminal_sessions):
            self.close_remote_terminal(terminal)
        try:
            if self.sftp:
                self.sftp.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = Tk()
    app = ComfyRemoteManager(root)
    root.mainloop()
