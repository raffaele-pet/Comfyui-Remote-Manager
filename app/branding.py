"""Shared Windows icon for the app and setup wizards."""

from pathlib import Path


ICON_PATH = Path("assets") / "branding" / "comfyui-remote-manager.ico"


def apply_window_icon(window):
    icon = Path(__file__).resolve().parents[1] / ICON_PATH
    if icon.is_file():
        window.iconbitmap(default=str(icon))
