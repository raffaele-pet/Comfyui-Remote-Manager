param(
    [string]$ComfyPath,
    [string]$StartBatch,
    [string]$SshUser,
    [string]$ExportPath = (Join-Path ([Environment]::GetFolderPath('Desktop')) 'comfyui-remote-config.json')
)

$ErrorActionPreference = 'Stop'

function Find-Program([string]$Name, [string[]]$Candidates) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($candidate in $Candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    return $null
}

function Install-WingetPackage([string]$Id) {
    Write-Host "Installazione di $Id..."
    & winget.exe install --id $Id --exact --source winget --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "Installazione di $Id non riuscita (codice $LASTEXITCODE)." }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Apri PowerShell come amministratore e rilancia questo script.'
}
if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    throw 'WinGet non trovato. Installa App Installer di Microsoft, poi rilancia questo script.'
}

Write-Host '=== PC A: ComfyUI Portable, SSH, Tailscale e cloudflared ==='
while (-not $ComfyPath) { $ComfyPath = Read-Host 'Percorso completo della cartella ComfyUI Portable' }
$ComfyPath = (Resolve-Path -LiteralPath $ComfyPath).Path.TrimEnd('\')
$batches = @(Get-ChildItem -LiteralPath $ComfyPath -Filter 'run*.bat' -File | Select-Object -ExpandProperty Name)
if ($batches.Count -eq 0) { throw 'Nessun batch di avvio run*.bat nella cartella indicata.' }
if (-not $StartBatch) {
    Write-Host ('Batch disponibili: ' + ($batches -join ', '))
    $defaultBatch = if ($batches -contains 'run_nvidia_gpu.bat') { 'run_nvidia_gpu.bat' } else { $batches[0] }
    $StartBatch = Read-Host "Batch di avvio (INVIO per $defaultBatch)"
    if (-not $StartBatch) { $StartBatch = $defaultBatch }
}
if ($batches -notcontains $StartBatch) { throw "Batch non trovato: $StartBatch" }
if (-not (Test-Path -LiteralPath (Join-Path $ComfyPath 'python_embeded\python.exe') -PathType Leaf)) {
    throw 'Manca python_embeded\python.exe: serve ComfyUI Portable per Windows.'
}
if (-not $SshUser) {
    $SshUser = Read-Host "Utente Windows per SSH (INVIO per $env:USERNAME)"
    if (-not $SshUser) { $SshUser = $env:USERNAME }
}
if (-not (Get-LocalUser -Name $SshUser -ErrorAction SilentlyContinue)) {
    throw "Utente Windows inesistente: $SshUser"
}

if (-not (Get-Service sshd -ErrorAction SilentlyContinue)) {
    Write-Host 'Installazione del server OpenSSH di Windows...'
    $result = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
    if ($result.RestartNeeded) { throw 'Riavvia Windows e rilancia questo script per completare OpenSSH.' }
}
Set-Service -Name sshd -StartupType Automatic
Start-Service -Name sshd
if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
} else {
    Enable-NetFirewallRule -Name 'OpenSSH-Server-In-TCP'
}

$tailscale = Find-Program 'tailscale.exe' @('C:\Program Files\Tailscale\tailscale.exe')
if (-not $tailscale) {
    Install-WingetPackage 'Tailscale.Tailscale'
    $tailscale = Find-Program 'tailscale.exe' @('C:\Program Files\Tailscale\tailscale.exe')
}
if (-not $tailscale) { throw 'Tailscale installato ma non trovato. Apri un nuovo PowerShell e rilancia lo script.' }

Write-Host 'Accedi a Tailscale dal browser tramite l''icona nell''area di notifica.'
Write-Host 'Usa la stessa tailnet che userai su PC B. Poi torna qui.'
$tailscaleIp = ''
while (-not $tailscaleIp) {
    Read-Host 'Premi INVIO dopo aver completato l''accesso a Tailscale' | Out-Null
    $ipResult = & $tailscale ip -4 2>$null | Select-Object -First 1
    if ($ipResult) { $tailscaleIp = $ipResult.Trim() }
    if (-not $tailscaleIp) { Write-Host 'Nessun IP Tailscale rilevato. Completa l''accesso e riprova.' }
}
Write-Host 'Per raggiungere PC A anche senza accesso a Windows, abilita Run Unattended dal menu Tailscale.'
& $tailscale up --unattended=true
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Run Unattended non attivato automaticamente: abilitalo dal menu Tailscale.'
}

$cloudflared = Find-Program 'cloudflared.exe' @('C:\Program Files\Cloudflare\Cloudflared\cloudflared.exe')
if (-not $cloudflared) {
    Install-WingetPackage 'Cloudflare.cloudflared'
    $cloudflared = Find-Program 'cloudflared.exe' @('C:\Program Files\Cloudflare\Cloudflared\cloudflared.exe')
}
if (-not $cloudflared) {
    $packageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
    $cloudflared = Get-ChildItem -LiteralPath $packageRoot -Filter 'cloudflared.exe' -Recurse -File -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $cloudflared) { throw 'cloudflared installato ma non trovato. Apri un nuovo PowerShell e rilancia lo script.' }
$binDir = Join-Path $env:ProgramData 'ComfyUIRemoteManager'
New-Item -ItemType Directory -Path $binDir -Force | Out-Null
$stableCloudflared = Join-Path $binDir 'cloudflared.exe'
Copy-Item -LiteralPath $cloudflared -Destination $stableCloudflared -Force
$cloudflared = $stableCloudflared

$config = [ordered]@{
    version = 1
    host = $tailscaleIp
    port = 22
    user = $SshUser
    comfy_dir = $ComfyPath
    start_batch = $StartBatch
    cloudflared_exe = $cloudflared
}
$config | ConvertTo-Json | Set-Content -LiteralPath $ExportPath -Encoding UTF8
Write-Host "Configurazione esportata: $ExportPath"
Write-Host 'Copia quel file su PC B. La password Windows non e inclusa: la inserirai nell''app.'
Write-Host 'Cloudflare Quick Tunnel viene avviato dall''app quando premi Avvia; non richiede un account Cloudflare.'
