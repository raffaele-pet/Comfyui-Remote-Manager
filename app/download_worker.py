"""Executed in memory by ComfyUI Remote Manager on the remote PC."""

import json
import os
import re
import time
import urllib.parse
import urllib.request
from email.message import Message
from pathlib import Path


def format_size(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def safe_filename(value):
    value = urllib.parse.unquote(value or "").strip().strip('"')
    value = re.sub(r'[<>:"/\\|?*]+', "_", value).rstrip(" .")
    return value or "downloaded_model"


def response_filename(headers, url):
    disposition = headers.get("Content-Disposition")
    if disposition:
        message = Message()
        message["content-disposition"] = disposition
        for key, value in message.get_params(header="content-disposition", failobj=[]):
            if key.lower() == "filename*":
                parts = str(value).split("'", 2)
                if len(parts) == 3:
                    return urllib.parse.unquote(parts[2])
            if key.lower() == "filename":
                return value
    return os.path.basename(urllib.parse.urlparse(url).path)


def main(config):
    url = config["url"].strip()
    destination = Path(config["dest_dir"])
    destination.mkdir(parents=True, exist_ok=True)
    headers = {"User-Agent": "ComfyUI-Remote-Manager"}
    if config.get("token"):
        headers["Authorization"] = "Bearer " + config["token"]

    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        final_url = response.geturl()
        filename = safe_filename(config.get("filename") or response_filename(response.headers, final_url))
        length = response.headers.get("Content-Length", "")
        total = int(length) if length.isdigit() else 0

    target = destination / filename
    existing = target.stat().st_size if target.exists() else 0
    if total and existing == total:
        print("File gia presente e completo: " + str(target), flush=True)
        return

    resume = bool(total and 0 < existing < total)
    if resume:
        headers["Range"] = f"bytes={existing}-"

    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        mode = "ab" if resume and response.status == 206 else "wb"
        downloaded = existing if mode == "ab" else 0
        if not total:
            length = response.headers.get("Content-Length", "")
            total = int(length) + downloaded if length.isdigit() else 0
        started = time.monotonic()
        last_report = 0
        print("Destinazione: " + str(target), flush=True)
        with target.open(mode) as output:
            while True:
                chunk = response.read(8 * 1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_report >= 2 or (total and downloaded >= total):
                    speed = (downloaded - (existing if mode == "ab" else 0)) / max(now - started, 0.1)
                    if total:
                        percent = min(downloaded / total * 100, 100)
                        print(f"DOWNLOAD_PROGRESS {percent:.1f}%  {format_size(downloaded)} / {format_size(total)}  {format_size(speed)}/s", flush=True)
                    else:
                        print(f"DOWNLOAD_PROGRESS {format_size(downloaded)}  {format_size(speed)}/s", flush=True)
                    last_report = now
    print("REMOTE_DOWNLOAD_DONE", flush=True)
