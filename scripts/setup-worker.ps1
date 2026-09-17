<#
.SYNOPSIS
    Zenith Antigravity Worker Bootstrapper & Lifecycle Orchestrator for Windows.
.DESCRIPTION
    Installs Antigravity CLI (agy.exe), prepares worker virtualenv, and manages background daemon.
.PARAMETER Action
    install, start, stop, restart, status, or install-and-start.
#>
param(
    [Parameter(Position=0)]
    [ValidateSet("install", "start", "stop", "restart", "status", "install-and-start", "login")]
    [string]$Action = "install-and-start"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path

$WorkerDir = Join-Path $RootDir "worker"
$WorkerVenv = Join-Path $WorkerDir ".venv"
$RootVenv = Join-Path $RootDir ".venv"

function Ensure-Path {
    $localAgy = Join-Path $env:LOCALAPPDATA "agy\bin"
    if ((Test-Path $localAgy) -and ($env:PATH -notlike "*$localAgy*")) {
        $env:PATH = "$localAgy;$env:PATH"
    }
}

function Install-Agy {
    Ensure-Path
    $found = Get-Command agy.exe -ErrorAction SilentlyContinue
    if (-not $found) {
        $found = Get-Command agy -ErrorAction SilentlyContinue
    }
    if ($found) {
        Write-Host "  [OK] Antigravity CLI (agy) found at: $($found.Source)" -ForegroundColor Green
        return
    }

    $defaultPath = Join-Path $env:LOCALAPPDATA "agy\bin\agy.exe"
    if (Test-Path $defaultPath) {
        Write-Host "  [OK] Antigravity CLI (agy) found at: $defaultPath" -ForegroundColor Green
        Ensure-Path
        return
    }

    Write-Host "  [INFO] Antigravity CLI not found. Installing via official Google installer..." -ForegroundColor Cyan
    try {
        Invoke-Expression (Invoke-RestMethod -Uri "https://antigravity.google/cli/install.ps1")
        Ensure-Path
        Write-Host "  [OK] Antigravity CLI installed successfully." -ForegroundColor Green
    }
    catch {
        Write-Host "  [WARN] Failed to automatically download agy CLI: $_" -ForegroundColor Yellow
        Write-Host "  Manual install: irm https://antigravity.google/cli/install.ps1 | iex" -ForegroundColor DarkGray
    }
}

function Setup-Venv {
    $targetVenv = $WorkerVenv
    $targetPy = Join-Path $targetVenv "Scripts\python.exe"

    if (-not (Test-Path $targetPy)) {
        $rootPy = Join-Path $RootVenv "Scripts\python.exe"
        if (Test-Path $rootPy) {
            $targetVenv = $RootVenv
            $targetPy = $rootPy
        }
    }

    if (-not (Test-Path $targetPy)) {
        Write-Host "  [INFO] Creating worker virtual environment in worker\.venv..." -ForegroundColor Cyan
        $sysPy = (Get-Command python.exe -ErrorAction SilentlyContinue)
        if ($sysPy) {
            & python -m venv $WorkerVenv
            $targetVenv = $WorkerVenv
            $targetPy = Join-Path $targetVenv "Scripts\python.exe"
        }
        else {
            Write-Host "  [ERR] Python is required to run the Antigravity worker." -ForegroundColor Red
            return
        }
    }

    $pipExe = Join-Path $targetVenv "Scripts\pip.exe"
    $reqFile = Join-Path $WorkerDir "requirements.txt"
    if ((Test-Path $pipExe) -and (Test-Path $reqFile)) {
        Write-Host "  [INFO] Installing worker requirements (fastapi, uvicorn)..." -ForegroundColor Cyan
        & $pipExe install -q -r $reqFile
        Write-Host "  [OK] Worker environment ready." -ForegroundColor Green
    }
}

function Resolve-PythonExecutable {
    $wPy = Join-Path $WorkerVenv "Scripts\python.exe"
    if (Test-Path $wPy) { return $wPy }
    $rPy = Join-Path $RootVenv "Scripts\python.exe"
    if (Test-Path $rPy) { return $rPy }
    return "python"
}

Push-Location $RootDir
try {
    Ensure-Path
    $py = Resolve-PythonExecutable

    switch ($Action) {
        "install" {
            Install-Agy
            Setup-Venv
        }
        "start" {
            & $py -m worker.manage start
        }
        "stop" {
            & $py -m worker.manage stop
        }
        "restart" {
            & $py -m worker.manage restart
        }
        "status" {
            & $py -m worker.manage status
        }
        "install-and-start" {
            Install-Agy
            Setup-Venv
            & $py -m worker.manage start
        }
        "login" {
            Install-Agy
            & $py -m worker.manage login
        }
    }
}
finally {
    Pop-Location
}
