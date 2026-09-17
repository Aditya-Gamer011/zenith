@echo off
setlocal enabledelayedexpansion
title Zenith — Autonomous AI Operating Layer
cd /d "%~dp0"

if exist "%~dp0zenith.exe" (
    "%~dp0zenith.exe" %*
    exit /b !ERRORLEVEL!
)

where pwsh.exe >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PS_CMD=pwsh.exe"
) else (
    set "PS_CMD=powershell.exe"
)

if exist "%~dp0zenith-install.ps1" (
    set "SCRIPT_PATH=%~dp0zenith-install.ps1"
) else if exist "%~dp0scripts\zenith-install.ps1" (
    set "SCRIPT_PATH=%~dp0scripts\zenith-install.ps1"
) else if exist "%USERPROFILE%\.zenith\app\zenith-install.ps1" (
    set "SCRIPT_PATH=%USERPROFILE%\.zenith\app\zenith-install.ps1"
) else (
    echo [Zenith Error] Could not locate zenith-install.ps1.
    pause
    exit /b 1
)

"%PS_CMD%" -NoProfile -ExecutionPolicy Bypass -File "!SCRIPT_PATH!" %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% neq 0 (
    echo.
    echo [Zenith] Execution ended with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
