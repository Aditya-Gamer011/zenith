<#
.SYNOPSIS
    Creates a Windows desktop shortcut for Zenith.exe.
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = (Resolve-Path (Join-Path $ScriptDir "..")).Path

$TargetExe = Join-Path $RootDir "zenith.exe"
if (-not (Test-Path $TargetExe)) {
    $TargetExe = Join-Path $RootDir "start.bat"
}

$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "Zenith.lnk"

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $TargetExe
    $Shortcut.WorkingDirectory = $RootDir
    $Shortcut.Description = "Zenith - Autonomous AI Operating Layer"
    $Shortcut.Save()
    Write-Host "Desktop shortcut created: $ShortcutPath" -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not create desktop shortcut: $_" -ForegroundColor Yellow
}
