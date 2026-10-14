# ComfyUI Remote Manager

ComfyUI Remote Manager is a Windows desktop app for running and managing ComfyUI Portable on another computer. The **PC Server** hosts ComfyUI; the **PC Client** runs this app. They connect through Tailscale and SSH. Starting ComfyUI also starts a Cloudflare Quick Tunnel and displays its public link in the app.

Both installers and the app support English and Italian. Each installer asks for a language before setup begins, with English selected by default. The PC Client installer sets the app's initial language to your selection. In the app, change **Language** in the left sidebar; the choice is saved immediately for future launches. When running the app directly without an installer or saved preference, English is the default.

## Install the PC Server

The PC Server needs the Windows portable edition of ComfyUI, with a `run*.bat` launcher and `python_embeded\python.exe` in its main folder. The Windows account used for SSH must have a password; a Windows Hello PIN is not sufficient.

1. Download [install-server.exe](./install-server.exe) on the PC Server and open it. Approve the Windows administrator prompt.
2. Choose a language, the ComfyUI Portable folder, a startup batch file, and the Windows account to use for SSH. The installer prepares OpenSSH Server, Tailscale, and `cloudflared`.
3. Open Tailscale from the installer, sign in, and verify the connection. Use the same tailnet on both computers. If unattended mode cannot be enabled automatically, enable it in Tailscale's settings.
4. Verify `cloudflared`, then save `comfyui-remote-config.json` and copy it to the PC Client. The file contains connection settings and paths, but no password.

## Install the PC Client

1. Download [install-client.exe](./install-client.exe) on the PC Client and open it. The installer contains the app files, so Git is not required.
2. Choose a language and start the installation. The installer prepares Tailscale, Python, the app dependencies, `run.bat`, and a Desktop shortcut.
3. Sign in to Tailscale with the same tailnet as the PC Server, then verify the connection.
4. Import the configuration file from the PC Server, enter its settings manually, or close the installer and enter them in the app. Enter the SSH password in the app.

Open **ComfyUI Remote Manager** from the Desktop shortcut. To update an existing PC Client installation, download and run the latest `install-client.exe` again.

The installers target Windows x64. Installing components and Python packages requires an internet connection and WinGet. The setup wizard source files are `install_server.py`, `install_client.py`, and `installer_common.py`; translations are in `localization.py`.

## Change the ComfyUI folder or Windows user

If ComfyUI is moved or renamed on the PC Server, update **ComfyUI Portable folder** and, if needed, **Startup batch file** in the PC Client app. Select **Save folder and batch file**. The new path is used for start, stop, update, remote file shortcuts, and direct URL downloads. If the PC Server's Windows user changes, update **User** and reconnect.

**Save folder and batch file** is disabled when the saved folder and batch file are already current. It becomes available when they are missing, changed, or imported from a new configuration file.

The connection profile is stored on the PC Client at `%LOCALAPPDATA%\ComfyUIRemoteManager\connection.json`. Language preference is stored separately at `%LOCALAPPDATA%\ComfyUIRemoteManager\preferences.json`. Saving the SSH password is optional; when enabled, it is protected with Windows encryption. The app does not create report, link, or download configuration files on the PC Server Desktop.

## Features

- Check, start, stop, and update ComfyUI remotely.
- Start Cloudflare and display the public link in the app.
- Browse files over SFTP; upload, download, preview, rename, move, and delete them.
- Download a URL directly on the PC Server without installing a persistent helper there.
- Use an SSH PowerShell terminal and edit remote text files. Press Enter to run a command and Ctrl+C to interrupt it; Ctrl+C copies text when a selection is active.

**PC Server shortcuts** has two rows: User home, Desktop, and Recycle Bin; then ComfyUI Portable, custom nodes, models, diffusion models, text encoders, vae, and loras. The sidebar groups connection settings, ComfyUI settings, and language selection. Open the terminal from the file browser toolbar. The names **PC Server** and **PC Client** stay the same in both languages.

## Start ComfyUI locally after using it remotely

Download [run_nvidia_gpu_close_instances.bat](./run_nvidia_gpu_close_instances.bat) and place it alongside `run_nvidia_gpu.bat` in the ComfyUI Portable folder on the PC Server. Use this additional launcher to close previous ComfyUI instances, verify that port 8188 is free, and then start ComfyUI with `--windows-standalone-build --listen 0.0.0.0 --enable-manager --enable-manager-legacy-ui`. Closing an instance interrupts its running jobs.

The launcher uses its own folder, so moving or renaming ComfyUI Portable does not require editing the batch file. A local launch opens `http://127.0.0.1:8188` in the default browser when ComfyUI is ready, including when cleanup needs administrator permission. Over SSH, the browser stays closed on the PC Server. It needs no separate cleanup script or Desktop log files. When closing an instance requires administrator permission, a local launch asks for it. Over SSH, a permission error stops startup and appears in the app. If another application owns port 8188, the launcher reports it and stops. To use this additional launcher from the app, set **Startup batch file** to `run_nvidia_gpu_close_instances.bat` and save it.

The temporary `trycloudflare.com` link is public. [Cloudflare describes Quick Tunnels as suitable for testing and development](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/); do not use the link for data that must stay private.

Desktop shortcut icon: [Icons8](https://icons8.it/icon/rJGwKUDZzg4L/ai). To rebuild the installers on Windows, install PyInstaller and run `py build_installers.py`.
