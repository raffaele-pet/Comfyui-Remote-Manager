# ComfyUI Remote Manager

ComfyUI Remote Manager is a Windows desktop app for running and managing ComfyUI Portable on another computer. The **Server PC** hosts ComfyUI; the **User PC** runs this app. They connect through Tailscale and SSH. Starting ComfyUI also starts a Cloudflare Quick Tunnel and displays its public link in the app.

Both installers and the app support English and Italian. English is the default. Each installer asks for a language before setup begins. In the app, change **Language** in the left sidebar; the choice is saved immediately for future launches.

## Install the Server PC

The Server PC needs the Windows portable edition of ComfyUI, with a `run*.bat` launcher and `python_embeded\python.exe` in its main folder. The Windows account used for SSH must have a password; a Windows Hello PIN is not sufficient.

1. Download [install-server.exe](./install-server.exe) on the Server PC and open it. Approve the Windows administrator prompt.
2. Choose a language, the ComfyUI Portable folder, a startup batch file, and the Windows account to use for SSH. The installer prepares OpenSSH Server, Tailscale, and `cloudflared`.
3. Open Tailscale from the installer, sign in, and verify the connection. Use the same tailnet on both computers. If unattended mode cannot be enabled automatically, enable it in Tailscale's settings.
4. Verify `cloudflared`, then save `comfyui-remote-config.json` and copy it to the User PC. The file contains connection settings and paths, but no password.

## Install the User PC

1. Download [install-user.exe](./install-user.exe) on the User PC and open it. The installer contains the app files, so Git is not required.
2. Choose a language and start the installation. The installer prepares Tailscale, Python, the app dependencies, `run.bat`, and a Desktop shortcut.
3. Sign in to Tailscale with the same tailnet as the Server PC, then verify the connection.
4. Import the configuration file from the Server PC, enter its settings manually, or close the installer and enter them in the app. Enter the SSH password in the app.

Open **ComfyUI Remote Manager** from the Desktop shortcut. To update an existing User PC installation, download and run the latest `install-user.exe` again.

The installers target Windows x64. Installing components and Python packages requires an internet connection and WinGet. The setup wizard source files are `install_server.py`, `install_user.py`, and `installer_common.py`; translations are in `localization.py`.

## Change the ComfyUI folder or Windows user

If ComfyUI is moved or renamed on the Server PC, update **ComfyUI Portable folder on Server PC** and, if needed, **Startup batch file** in the User PC app. Select **Save folder and batch file**. The new path is used for start, stop, update, remote file shortcuts, and direct URL downloads. If the Server PC's Windows user changes, update **User** and reconnect.

**Save folder and batch file** is disabled when the saved folder and batch file are already current. It becomes available when they are missing, changed, or imported from a new configuration file.

The connection profile is stored on the User PC at `%LOCALAPPDATA%\ComfyUIRemoteManager\connection.json`. Language preference is stored separately at `%LOCALAPPDATA%\ComfyUIRemoteManager\preferences.json`. Saving the SSH password is optional; when enabled, it is protected with Windows encryption. The app does not create report, link, or download configuration files on the Server PC Desktop.

## Features

- Check, start, stop, and update ComfyUI remotely.
- Start Cloudflare and display the public link in the app.
- Browse files over SFTP; upload, download, preview, rename, move, and delete them.
- Download a URL directly on the Server PC without installing a persistent helper there.
- Use a persistent SSH PowerShell terminal and edit remote text files.

The temporary `trycloudflare.com` link is public. [Cloudflare describes Quick Tunnels as suitable for testing and development](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/); do not use the link for data that must stay private.

Desktop shortcut icon: [Icons8](https://icons8.it/icon/rJGwKUDZzg4L/ai). To rebuild the installers on Windows, install PyInstaller and run `py build_installers.py`.
