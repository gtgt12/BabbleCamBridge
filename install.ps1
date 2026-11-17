# BabbleCamBridge installer: installs Python and FFmpeg if missing (via winget), sets up a private Python
# environment in this folder, and creates desktop shortcuts. Safe to run again (e.g. after updating).
param([switch]$NoShortcuts)
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here

function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Find-Python {
    foreach ($c in @(@('py', '-3.12'), @('py', '-3.11'), @('py', '-3.13'), @('py', '-3'), @('python'))) {
        try {
            $v = & $c[0] $c[1..9] -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($LASTEXITCODE -eq 0 -and $v -match '^3\.(1[0-9])$') { return , $c }
        } catch { }
    }
    return $null
}

Write-Host '== BabbleCamBridge setup ==' -ForegroundColor Cyan
$py = Find-Python
if (-not $py) {
    Write-Host 'Python not found, installing Python 3.12 (winget)...'
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    $py = Find-Python
    if (-not $py) { throw 'Python could not be installed. Install Python 3.12 from python.org, then run install.bat again.' }
}
Write-Host ('Python: ' + ($py -join ' '))

Refresh-Path
$ff = Get-Command ffmpeg -ErrorAction SilentlyContinue | Where-Object { (Get-Item $_.Source).Length -gt 100000 }
if (-not $ff) {
    $ff = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
}
if (-not $ff) {
    Write-Host 'FFmpeg not found, installing FFmpeg (winget)...'
    winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    Write-Host 'Creating Python environment...'
    & $py[0] $py[1..9] -m venv .venv
}
& .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --upgrade pip
& .venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt
& .venv\Scripts\python.exe -c "import tkinter, numpy, PIL; print('libraries OK')"
& .venv\Scripts\python.exe bridge\devices.py

if (-not $NoShortcuts) {
    $desk = [Environment]::GetFolderPath('Desktop')
    $sh = New-Object -ComObject WScript.Shell
    $pyw = Join-Path $here '.venv\Scripts\pythonw.exe'
    foreach ($s in @(@('BabbleCamBridge', 'bridge\gui.py'), @('BabbleCamBridge (background)', 'bridge\server.py'))) {
        $l = $sh.CreateShortcut((Join-Path $desk ($s[0] + '.lnk')))
        $l.TargetPath = $pyw
        $l.Arguments = '"' + (Join-Path $here $s[1]) + '"'
        $l.WorkingDirectory = Join-Path $here 'bridge'
        $l.IconLocation = "$env:SystemRoot\System32\imageres.dll,-5338"
        $l.Save()
    }
    Write-Host 'Desktop shortcuts created: "BabbleCamBridge" (window) and "BabbleCamBridge (background)".'
}
Write-Host 'Done. Open "BabbleCamBridge" on your desktop to pick your cameras.' -ForegroundColor Green
