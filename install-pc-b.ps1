param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\ComfyUIRemoteManager'),
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'
$repository = 'https://github.com/raffaele-pet/comfyui-remote-manager.git'
$appDir = Join-Path $InstallDir 'app'
$venvDir = Join-Path $InstallDir '.venv'
$requiredFiles = @('comfyui_remote_manager.py', 'download_worker.py', 'requirements.txt', 'run.bat')

function Install-WingetPackage([string]$Id) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet non trovato. Installa App Installer di Microsoft e rilancia lo script.'
    }
    Write-Host "Installazione di $Id..."
    & winget.exe install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Installazione di $Id non riuscita (codice $LASTEXITCODE)." }
}

Write-Host '=== PC B: Tailscale e ComfyUI Remote Manager ==='
$tailscale = Get-Command tailscale.exe -ErrorAction SilentlyContinue
if (-not $tailscale -and -not (Test-Path -LiteralPath 'C:\Program Files\Tailscale\tailscale.exe')) {
    Install-WingetPackage 'Tailscale.Tailscale'
}
$tailscaleExe = if (Test-Path -LiteralPath 'C:\Program Files\Tailscale\tailscale.exe') {
    'C:\Program Files\Tailscale\tailscale.exe'
} else {
    (Get-Command tailscale.exe -ErrorAction Stop).Source
}
Write-Host 'Accedi a Tailscale dall''icona nell''area di notifica, usando la stessa tailnet di PC A.'
$tailscaleIp = ''
while (-not $tailscaleIp) {
    Read-Host 'Premi INVIO dopo aver completato l''accesso a Tailscale' | Out-Null
    $ipResult = & $tailscaleExe ip -4 2>$null | Select-Object -First 1
    if ($ipResult) { $tailscaleIp = $ipResult.Trim() }
    if (-not $tailscaleIp) { Write-Host 'Nessun IP Tailscale rilevato. Completa l''accesso e riprova.' }
}

$localSource = $requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $_) -PathType Leaf) }
if ($localSource.Count -eq 0) {
    New-Item -ItemType Directory -Path $appDir -Force | Out-Null
    if ((Resolve-Path -LiteralPath $PSScriptRoot).Path -ne (Resolve-Path -LiteralPath $appDir).Path) {
        foreach ($name in $requiredFiles) {
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $appDir $name) -Force
        }
    }
} elseif (Test-Path -LiteralPath (Join-Path $appDir 'comfyui_remote_manager.py')) {
    Write-Host 'Uso la copia dell''app gia installata.'
} else {
    $gitExe = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
    if (-not $gitExe -and (Test-Path -LiteralPath 'C:\Program Files\Git\cmd\git.exe')) {
        $gitExe = 'C:\Program Files\Git\cmd\git.exe'
    }
    if (-not $gitExe) {
        Install-WingetPackage 'Git.Git'
        $gitExe = 'C:\Program Files\Git\cmd\git.exe'
    }
    if (-not (Test-Path -LiteralPath $gitExe)) { throw 'Git non trovato dopo l''installazione.' }
    Write-Host 'Scarico il repository. Se GitHub richiede l''accesso, completa la procedura nel browser.'
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    & $gitExe clone $repository $appDir
    if ($LASTEXITCODE -ne 0) { throw 'Clone GitHub non riuscito. Verifica l''accesso al repository e riprova.' }
}

$launcher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
$python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $launcher -and (-not $python -or $python -like '*WindowsApps*')) {
    Install-WingetPackage 'Python.Python.3.13'
    $launcher = (Get-Command py.exe -ErrorAction SilentlyContinue).Source
    $python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'
    if (-not (Test-Path -LiteralPath $python)) {
        $python = 'C:\Program Files\Python313\python.exe'
    }
}
if (-not $launcher -and (-not $python -or -not (Test-Path -LiteralPath $python))) {
    throw 'Python non trovato dopo l''installazione. Apri un nuovo PowerShell e rilancia lo script.'
}

if (-not (Test-Path -LiteralPath (Join-Path $venvDir 'Scripts\python.exe'))) {
    if ($launcher) { & $launcher -3 -m venv $venvDir }
    else { & $python -m venv $venvDir }
    if ($LASTEXITCODE -ne 0) { throw 'Creazione dell''ambiente Python non riuscita.' }
}
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
& $venvPython -m pip install -r (Join-Path $appDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installazione delle dipendenze Python non riuscita.' }

if ($ConfigPath) {
    $config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($config.version -ne 1 -or -not $config.host -or -not $config.user -or -not $config.comfy_dir) {
        throw 'File di configurazione PC A non valido.'
    }
    $profileDir = Join-Path $env:LOCALAPPDATA 'ComfyUIRemoteManager'
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
    $profile = [ordered]@{
        host = $config.host
        port = $config.port
        user = $config.user
        comfy_dir = $config.comfy_dir
        start_batch = if ($config.start_batch) { $config.start_batch } else { 'run_nvidia_gpu.bat' }
        cloudflared_exe = if ($config.cloudflared_exe) { $config.cloudflared_exe } else { 'cloudflared' }
        remember_password = $false
        password = ''
    }
    $profile | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $profileDir 'connection.json') -Encoding UTF8
}

$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'ComfyUI Remote Manager.lnk'
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($startMenu)
$shortcut.TargetPath = Join-Path $appDir 'run.bat'
$shortcut.WorkingDirectory = $appDir
$shortcut.Save()
Write-Host "Installazione completata: $appDir"
Write-Host 'Apri ComfyUI Remote Manager dal menu Start. Importa la configurazione PC A oppure compila host, utente e percorso ComfyUI a mano.'
