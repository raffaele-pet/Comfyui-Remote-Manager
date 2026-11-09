param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Client', 'Server')]
    [string] $Role
)

$ErrorActionPreference = 'Stop'

function Test-Python {
    param([string] $Executable, [string[]] $Prefix = @())

    $probe = "import json, struct, sys, tkinter, venv; assert sys.version_info >= (3, 10) and struct.calcsize('P') == 8; print(json.dumps({'path': sys._base_executable}))"
    try {
        $result = & $Executable @Prefix -I -c $probe 2>$null | Select-Object -Last 1
        if ($LASTEXITCODE -eq 0 -and $result) {
            $base = (ConvertFrom-Json -InputObject $result).path
            if (-not $base -or -not [IO.Path]::IsPathRooted($base) -or
                -not (Test-Path -LiteralPath $base -PathType Leaf)) { return }
            $guiPython = Join-Path (Split-Path -LiteralPath $base) 'pythonw.exe'
            if (Test-Path -LiteralPath $guiPython -PathType Leaf) {
                return $guiPython
            }
        }
    } catch {
        # An alias or a stale registration may point to a missing interpreter.
    }
}

function Find-Python {
    $candidates = @(
        Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike '*\WindowsApps\*' } |
            ForEach-Object { $_.Source }
    )
    $localPython = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Python'
    $programFiles = [Environment]::GetFolderPath('ProgramFiles')
    foreach ($parent in @($localPython, $programFiles)) {
        $candidates += @(Get-ChildItem -Path (Join-Path $parent 'Python*') -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | ForEach-Object { Join-Path $_.FullName 'python.exe' })
    }

    foreach ($registry in @('HKCU:\Software\Python\PythonCore', 'HKLM:\Software\Python\PythonCore',
                            'HKLM:\Software\WOW6432Node\Python\PythonCore')) {
        foreach ($key in (Get-ChildItem -LiteralPath $registry -ErrorAction SilentlyContinue)) {
            $entry = Get-Item -LiteralPath ($key.PSPath + '\InstallPath') -ErrorAction SilentlyContinue
            if ($entry) {
                $executable = $entry.GetValue('ExecutablePath')
                if ($executable) {
                    $candidates += $executable
                } elseif ($entry.GetValue('')) {
                    $candidates += Join-Path ($entry.GetValue('')) 'python.exe'
                }
            }
        }
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $python = Test-Python -Executable $candidate
            if ($python) { return $python }
        }
    }
    $launcher = Get-Command py.exe -CommandType Application -ErrorAction SilentlyContinue
    if ($launcher) {
        return Test-Python -Executable $launcher.Source -Prefix @('-3')
    }
}

$python = Find-Python
if (-not $python) {
    $winget = Get-Command winget.exe -CommandType Application -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Install Python 3.10 or newer (64-bit, with Tcl/Tk), or install Microsoft App Installer to enable WinGet.'
    }
    Write-Host 'Preparing Python for ComfyUI Remote Manager...'
    & $winget.Source install --id Python.Python.3.13 --exact --source winget --silent --accept-source-agreements --accept-package-agreements
    $python = Find-Python
    if (-not $python) {
        throw 'A working 64-bit Python installation with Tcl/Tk could not be found.'
    }
}

$launch = @{
    FilePath = $python
    ArgumentList = @('-E', '-s', '-m', "installer.install_$($Role.ToLowerInvariant())")
    WorkingDirectory = Split-Path -Parent $PSScriptRoot
}
if ($Role -eq 'Server') {
    $launch.Verb = 'RunAs'
}
Start-Process @launch
