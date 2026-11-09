"""Files shared by the source installation and standalone installers."""

import sys
from pathlib import Path

from app.branding import ICON_PATH


APP_FILES = (
    "__init__.py", "branding.py", "comfyui_remote_manager.py", "download_worker.py", "localization.py",
    "platform_paths.py", "terminal_display.py", "ui_theme.py", "requirements.txt",
)
LOCAL_LAUNCHER = "run_nvidia_gpu_close_instances.bat"


def resource_path(*parts):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root.joinpath(*parts)
