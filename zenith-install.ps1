<#
.SYNOPSIS
    Zenith Cognitive Operating Layer — Unified Windows PowerShell Bootstrapper
    Cross-platform installer, health inspector, and container orchestrator.

.DESCRIPTION
    Automates host system detection, profile generation, Docker & Compose validation,
    .env synchronization without secret leaks, container compilation, health checks,
    and automated browser launching.

.PARAMETER Repair
    Rebuilds Docker images without cache, repairs volume permissions, and restarts services.

.PARAMETER Update
    Pulls latest git commits, rebuilds containers, and restarts services.

.PARAMETER Uninstall
    Stops containers and provides interactive prompts to preserve or remove data.

.PARAMETER Stop
    Stops running Zenith containers.

.PARAMETER Restart
    Restarts Zenith container services.

.PARAMETER Logs
    Streams live container log output.

.PARAMETER Status
    Displays healthcheck inspection and host profile data.

.PARAMETER Yes
    Non-interactive execution mode (auto-accept prompts).

.EXAMPLE
    .\zenith-install.ps1
    .\zenith-install.ps1 -Repair
    .\zenith-install.ps1 -Logs
#>

[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$Update,
    [switch]$Uninstall,
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Logs,
    [switch]$Status,
    [Alias("y", "non-interactive")]
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$ZenithVersion = "2.1.0"
$DefaultPort = 8005
$ProfileDir = Join-Path $HOME ".zenith"
$ProfileFile = Join-Path $ProfileDir "system-info.json"
$RepoUrl = "https://github.com/Aditya-Gamer011/zenith.git"

function Write-StageHeader([string]$text) {
    Write-Host "`n$text" -ForegroundColor Cyan
}

function Write-Info([string]$text) {
    Write-Host "  ℹ  $text" -ForegroundColor Gray
}

function Write-Ok([string]$text) {
    Write-Host "  ✔  $text" -ForegroundColor Green
}

function Write-Warn([string]$text) {
    Write-Host "  ⚠️  $text" -ForegroundColor Yellow
}

function Write-Err([string]$text) {
    Write-Host "  ✖  $text" -ForegroundColor Red
}

function Prompt-Confirm([string]$prompt, [string]$defaultChoice = "y") {
    if ($Yes) { return $true }
    $choicePrompt = if ($defaultChoice -eq "y") { "[Y/n]" } else { "[y/N]" }
    Write-Host -NoNewline "  $prompt $choicePrompt : " -ForegroundColor White
    $ans = Read-Host
    if ([string]::IsNullOrWhiteSpace($ans)) { $ans = $defaultChoice }
    return ($ans -match '^(y|yes)$')
}

function Show-Banner {
    Write-Host "  ███████╗███████╗███╗   ██╗██╗████████╗██╗  ██╗" -ForegroundColor Cyan
    Write-Host "  ╚══███╔╝██╔════╝████╗  ██║██║╚══██╔══╝██║  ██║" -ForegroundColor Cyan
    Write-Host "    ███╔╝ █████╗  ██╔██╗ ██║██║   ██║   ███████║" -ForegroundColor Cyan
    Write-Host "   ███╔╝  ██╔══╝  ██║╚██╗██║██║   ██║   ██╔══██║" -ForegroundColor Cyan
    Write-Host "  ███████╗███████╗██║ ╚████║██║   ██║   ██║  ██║" -ForegroundColor Cyan
    Write-Host "  ╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═╝" -ForegroundColor Cyan
    Write-Host "  Autonomous AI Operating Layer • Windows Bootstrapper v$ZenithVersion`n" -ForegroundColor Gray
}

function Get-TargetPort {
    if ($env:ZENITH_PORT -and ($env:ZENITH_PORT -match '^\d+$')) {
        return [int]$env:ZENITH_PORT
    }
    if (Test-Path ".env") {
        foreach ($line in (Get-Content ".env" -ErrorAction SilentlyContinue)) {
            if ($line -match '^\s*ZENITH_PORT\s*=\s*(\d+)') {
                return [int]$Matches[1]
            }
        }
    }
    return $DefaultPort
}

# Auto-Install Prerequisites & Archive Retrieval (Standalone Support)
function Ensure-GitInstalled {
    if (Get-Command "git" -ErrorAction SilentlyContinue) {
        return $true
    }
    Write-Info "Git is not detected. Attempting automatic installation via winget..."
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            Start-Process -FilePath "winget" -ArgumentList "install --id Git.Git -e --source winget --silent --accept-source-agreements --accept-package-agreements" -Wait -NoNewWindow
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            if (Get-Command "git" -ErrorAction SilentlyContinue) {
                Write-Ok "Git installed successfully via winget."
                return $true
            }
        } catch { }
    }
    return $false
}

function Retrieve-RepoArchive {
    param([string]$Destination)
    Write-Info "Downloading Zenith repository archive directly from GitHub..."
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $zipUrl = "https://github.com/Aditya-Gamer011/zenith/archive/refs/heads/main.zip"
    $tempZip = Join-Path $env:TEMP "zenith-main-$([System.Guid]::NewGuid().ToString('N')).zip"
    $tempExtract = Join-Path $env:TEMP "zenith-extract-$([System.Guid]::NewGuid().ToString('N'))"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        Invoke-WebRequest -Uri $zipUrl -OutFile $tempZip -UseBasicParsing -ErrorAction Stop
        Expand-Archive -Path $tempZip -DestinationPath $tempExtract -Force
        $innerDir = Join-Path $tempExtract "zenith-main"
        if (Test-Path $innerDir) {
            Copy-Item -Path "$innerDir\*" -Destination $Destination -Recurse -Force
        } else {
            Copy-Item -Path "$tempExtract\*" -Destination $Destination -Recurse -Force
        }
        return (Test-Path (Join-Path $Destination "run.py"))
    } catch {
        Write-Warn "Archive retrieval failed: $_"
        return $false
    } finally {
        Remove-Item -Recurse -Force $tempZip -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force $tempExtract -ErrorAction SilentlyContinue
    }
}

function Ensure-PythonInstalled {
    if (Get-Command "python" -ErrorAction SilentlyContinue) {
        return $true
    }
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        return $true
    }
    Write-Info "Python is not detected. Attempting automatic installation..."
    $winget = Get-Command "winget" -ErrorAction SilentlyContinue
    if ($winget) {
        try {
            Write-Info "Installing Python 3.12 via winget..."
            Start-Process -FilePath "winget" -ArgumentList "install --id Python.Python.3.12 -e --source winget --silent --accept-source-agreements --accept-package-agreements" -Wait -NoNewWindow
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            if (Get-Command "python" -ErrorAction SilentlyContinue) {
                Write-Ok "Python installed successfully via winget."
                return $true
            }
        } catch { }
    }

    try {
        Write-Info "Downloading official Python installer from python.org..."
        $pyInstallerUrl = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"
        $pyInstallerPath = Join-Path $env:TEMP "python-installer.exe"
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
        Invoke-WebRequest -Uri $pyInstallerUrl -OutFile $pyInstallerPath -UseBasicParsing -ErrorAction Stop
        Write-Info "Running silent Python installation..."
        Start-Process -FilePath $pyInstallerPath -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0" -Wait
        Remove-Item -Force $pyInstallerPath -ErrorAction SilentlyContinue
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
        if (Get-Command "python" -ErrorAction SilentlyContinue) {
            Write-Ok "Python installed successfully."
            return $true
        }
    } catch {
        Write-Warn "Direct Python installer fallback encountered: $_"
    }
    return $false
}

# Resolve Workspace Location
function Resolve-Workspace {
    if ((Test-Path "run.py") -and (Test-Path "zenith") -and (Test-Path "Dockerfile")) {
        return (Get-Location).Path
    }
    elseif ((Test-Path "..\run.py") -and (Test-Path "..\zenith") -and (Test-Path "..\Dockerfile")) {
        Set-Location ".."
        return (Get-Location).Path
    }
    elseif (Test-Path (Join-Path $HOME ".zenith\app\run.py")) {
        $path = Join-Path $HOME ".zenith\app"
        Set-Location $path
        return $path
    }
    else {
        $dest = Join-Path $HOME ".zenith\app"
        New-Item -ItemType Directory -Force -Path (Join-Path $HOME ".zenith") | Out-Null
        if (-not (Test-Path (Join-Path $dest "run.py"))) {
            if (Test-Path $dest) {
                Remove-Item -Recurse -Force $dest -ErrorAction SilentlyContinue
            }
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
            $retrieved = $false
            if (Ensure-GitInstalled) {
                Write-Info "Cloning Zenith repository into $dest..."
                try {
                    git clone --depth 1 $RepoUrl $dest
                    if (Test-Path (Join-Path $dest "run.py")) {
                        $retrieved = $true
                    }
                } catch { }
            }
            if (-not $retrieved) {
                Write-Info "Git clone unavailable or failed; retrieving Zenith repository archive directly..."
                $retrieved = Retrieve-RepoArchive -Destination $dest
            }
            if ((-not $retrieved) -or (-not (Test-Path (Join-Path $dest "run.py")))) {
                Write-Err "Failed to retrieve Zenith repository. Please install git or download Zenith manually."
                exit 1
            }
            Write-Ok "Zenith repository successfully acquired."
        }
        Set-Location $dest
        return $dest
    }
}

function Find-DockerDesktopPath {
    $candidates = @(
        (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Docker\Docker Desktop.exe"),
        "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    try {
        $reg = Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Docker Desktop.exe" -ErrorAction SilentlyContinue
        if ($reg -and $reg.'(default)' -and (Test-Path $reg.'(default)')) {
            return $reg.'(default)'
        }
    } catch { }
    return $null
}

function Start-DockerEngine {
    $ddPath = Find-DockerDesktopPath
    if ($ddPath) {
        Write-Info "Docker Desktop is installed but stopped. Automatically starting engine ($ddPath)..."
        try {
            Start-Process -FilePath $ddPath
        } catch {
            Write-Warn "Could not launch Docker Desktop automatically: $_"
            return $false
        }
        Write-Host -NoNewline "  Waiting for Docker engine to ignite"
        for ($i = 1; $i -le 30; $i++) {
            Start-Sleep -Seconds 2
            Write-Host -NoNewline "•"
            try {
                $check = (docker info 2>$null)
                if ($LASTEXITCODE -eq 0) {
                    Write-Host ""
                    Write-Ok "Docker engine is online and responding!"
                    return $true
                }
            } catch { }
        }
        Write-Host ""
    }
    return $false
}

function Start-NativeZenithEngine {
    param([string]$Reason = "Container engine unavailable")
    Write-Warn "$Reason"
    Write-StageHeader "[Native Engine] Activating Zenith Native Host Mode..."

    $rootVenv = Join-Path $Workspace ".venv"
    $rootPy = Join-Path $rootVenv "Scripts\python.exe"

    if (-not (Test-Path $rootPy)) {
        if (-not (Get-Command "python" -ErrorAction SilentlyContinue) -and -not (Get-Command "py" -ErrorAction SilentlyContinue)) {
            Ensure-PythonInstalled | Out-Null
        }
        Write-Info "Bootstrapping Python virtual environment in .venv..."
        try {
            & python -m venv $rootVenv
        } catch {
            Write-Info "Retrying venv creation after ensuring Python packages..."
            Ensure-PythonInstalled | Out-Null
            try {
                & python -m venv $rootVenv
            } catch {
                Write-Err "Failed to create Python virtual environment: $_"
                exit 1
            }
        }
    }

    $pipExe = Join-Path $rootVenv "Scripts\pip.exe"
    $reqFile = Join-Path $Workspace "requirements.txt"
    if ((Test-Path $pipExe) -and (Test-Path $reqFile)) {
        try {
            & $rootPy -c "import fastapi, uvicorn" 2>$null
            if ($LASTEXITCODE -ne 0) {
                Write-Info "Installing Zenith dependencies..."
                & $pipExe install -q -r $reqFile
            }
        } catch {
            & $pipExe install -q -r $reqFile
        }
    }

    $nativePidFile = Join-Path $Workspace "data\zenith-native.pid"
    $nativeLogFile = Join-Path $Workspace "data\zenith-native.log"
    New-Item -ItemType Directory -Force -Path (Join-Path $Workspace "data") | Out-Null

    if (Test-Path $nativePidFile) {
        try {
            $oldPid = Get-Content $nativePidFile
            Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
        } catch { }
        Remove-Item $nativePidFile -Force -ErrorAction SilentlyContinue
    }

    $workerScript = Join-Path $Workspace "scripts\setup-worker.ps1"
    if (Test-Path $workerScript) {
        try { & $workerScript -Action "install-and-start" } catch { }
    }

    Write-Info "Starting Zenith Cognitive Operating Layer via run.py on port $TargetPort..."
    $proc = Start-Process -FilePath $rootPy -ArgumentList "run.py" -WorkingDirectory $Workspace -PassThru -WindowStyle Hidden
    Set-Content -Path $nativePidFile -Value $proc.Id -Encoding utf8
    Write-Ok "Zenith Native Engine started (PID $($proc.Id))"

    Write-StageHeader "Waiting for health checks..."
    $ready = $false
    Write-Host -NoNewline "  "
    for ($i = 1; $i -le 30; $i++) {
        Start-Sleep -Milliseconds 1200
        Write-Host -NoNewline "•"
        try {
            $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
            if ($resp.status -eq "ok" -or $resp.system -eq "Zenith") {
                $ready = $true
                break
            }
        } catch { }
    }
    # Create desktop shortcut
    $scScript = Join-Path $Workspace "scripts\create-windows-shortcut.ps1"
    if (Test-Path $scScript) {
        try { & $scScript } catch { }
    }

    if ($ready) {
        Write-Ok "Healthcheck verified: Zenith is online at $TargetUrl"
        try { Start-Process $TargetUrl } catch { }
        exit 0
    } else {
        Write-Err "Zenith Native Engine did not respond in time. Check $nativeLogFile"
        exit 1
    }
}

Show-Banner
$Workspace = Resolve-Workspace
Write-Info "Working directory: $Workspace"

$TargetPort = Get-TargetPort
$TargetUrl = "http://localhost:$TargetPort"
$HealthUrl = "$TargetUrl/api/health"

# Quick mode handlers
if ($Stop) {
    Write-StageHeader "Stopping Zenith services..."
    docker compose down 2>$null
    $nativePidFile = Join-Path $Workspace "data\zenith-native.pid"
    if (Test-Path $nativePidFile) {
        try {
            $nPid = Get-Content $nativePidFile
            Stop-Process -Id $nPid -Force -ErrorAction SilentlyContinue
            Remove-Item $nativePidFile -Force -ErrorAction SilentlyContinue
            Write-Ok "Native engine process stopped."
        } catch { }
    }
    $workerScript = Join-Path $Workspace "scripts\setup-worker.ps1"
    if (Test-Path $workerScript) {
        try { & $workerScript -Action stop } catch { }
    }
    Write-Ok "Zenith stopped."
    exit 0
}
if ($Restart) {
    Write-StageHeader "Restarting Zenith services..."
    docker compose restart
    $workerScript = Join-Path $Workspace "scripts\setup-worker.ps1"
    if (Test-Path $workerScript) {
        try { & $workerScript -Action restart } catch { }
    }
    Write-Ok "Zenith restarted."
    exit 0
}
if ($Logs) {
    docker compose logs -f
    exit 0
}
if ($Status) {
    Write-StageHeader "Zenith System & Container Status"
    if (Test-Path $ProfileFile) {
        Write-Host "Host Profile ($ProfileFile):" -ForegroundColor Gray
        Get-Content $ProfileFile
        Write-Host ""
    }
    docker compose ps
    Write-Host "`nHealthcheck (/api/health on port $TargetPort):" -ForegroundColor Gray
    try {
        $resp = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        $resp | ConvertTo-Json -Depth 3
    } catch {
        Write-Warn "Zenith is not responding on $TargetUrl"
    }
    $workerScript = Join-Path $Workspace "scripts\setup-worker.ps1"
    if (Test-Path $workerScript) {
        Write-Host "`nAntigravity Worker (port 8022):" -ForegroundColor Gray
        try { & $workerScript -Action status } catch { }
    }
    exit 0
}
if ($Uninstall) {
    Write-StageHeader "Zenith Safe Uninstaller"
    Write-Warn "This will stop and remove Zenith containers."
    if (Prompt-Confirm "Stop containers and networks?" "y") {
        docker compose down
        Write-Ok "Containers stopped."
    }
    if (Prompt-Confirm "Remove persistent volumes (data, memory, documents)?" "n") {
        docker compose down -v
        Write-Warn "Persistent volumes removed."
    }
    if (Prompt-Confirm "Remove system profile ($ProfileDir)?" "n") {
        Remove-Item -Recurse -Force $ProfileDir -ErrorAction SilentlyContinue
        Write-Ok "Profile directory removed."
    }
    Write-Ok "Uninstallation finished."
    exit 0
}

# ── STAGE 1: DETECTING SYSTEM ─────────────────────────────────────────────────
Write-StageHeader "[1/8] Detecting system..."

$OsInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$CpuInfo = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue
$GpuInfo = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue

$OsName = if ($OsInfo) { $OsInfo.Caption } else { [System.Environment]::OSVersion.VersionString }
$KernelVer = [System.Environment]::OSVersion.Version.ToString()
$Arch = if ([System.Environment]::Is64BitOperatingSystem) { "x86_64" } else { "x86" }
$CpuCores = if ($CpuInfo) { $CpuInfo.NumberOfLogicalProcessors } else { [System.Environment]::ProcessorCount }

$TotalRamMb = if ($OsInfo) { [math]::Round($OsInfo.TotalVisibleMemorySize / 1024) } else { 4096 }
$AvailRamMb = if ($OsInfo) { [math]::Round($OsInfo.FreePhysicalMemory / 1024) } else { 2048 }
$TotalRamGb = [math]::Round($TotalRamMb / 1024, 1)

$GpuList = if ($GpuInfo) { @($GpuInfo) } else { @() }
$NvidiaGpu = $GpuList | Where-Object { $_.Name -match "NVIDIA" } | Select-Object -First 1
$PrimaryGpu = if ($NvidiaGpu) { $NvidiaGpu } elseif ($GpuList.Count -gt 0) { $GpuList[0] } else { $null }
$GpuName = if ($PrimaryGpu) { $PrimaryGpu.Name } else { "None / Integrated" }
$GpuAvailable = ($GpuName -ne "None / Integrated")
$GpuIsNvidia = ($NvidiaGpu -ne $null)

$MemClass = if ($TotalRamMb -lt 2048) { "low" } elseif ($TotalRamMb -lt 8192) { "standard" } else { "high" }
$RecommendedWorkers = if ($TotalRamMb -lt 2048) { 1 } elseif ($TotalRamMb -lt 8192) { 2 } else { 4 }

# Save Profile (Zero secrets stored)
New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
$ProfileObject = [PSCustomObject]@{
    system = [PSCustomObject]@{
        os_family = "windows"
        os_name = $OsName
        distribution_id = "windows"
        distribution_version = $KernelVer
        kernel = $KernelVer
        architecture = $Arch
    }
    hardware = [PSCustomObject]@{
        cpu_cores = $CpuCores
        ram_total_mb = $TotalRamMb
        ram_total_gb = "$TotalRamGb"
        ram_available_mb = $AvailRamMb
        memory_class = $MemClass
        gpu = [PSCustomObject]@{
            available = $GpuAvailable
            type = if ($GpuIsNvidia) { "nvidia" } else { "integrated/discrete" }
            name = $GpuName
            cuda = $GpuIsNvidia
        }
    }
    user = [PSCustomObject]@{
        username = [System.Environment]::UserName
        domain = [System.Environment]::UserDomainName
    }
    runtime_adaptation = [PSCustomObject]@{
        recommended_workers = $RecommendedWorkers
        default_port = $TargetPort
        zenith_version = $ZenithVersion
        generated_at = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
}

$ProfileObject | ConvertTo-Json -Depth 4 | Set-Content -Path $ProfileFile -Encoding utf8
Write-Ok "Platform: $OsName ($Arch, Build $KernelVer)"
Write-Ok "Hardware: $CpuCores cores, $TotalRamGb GB RAM (Class: $MemClass)"
if ($GpuAvailable) { Write-Ok "Acceleration: $GpuName" }
Write-Ok "Profile saved: $ProfileFile (Zero secrets stored)"

# ── STAGE 2: CHECKING DOCKER ──────────────────────────────────────────────────
Write-StageHeader "[2/8] Checking Docker..."

$DockerReady = $false
$DockerInstalled = (Get-Command "docker" -ErrorAction SilentlyContinue) -ne $null

if ($DockerInstalled) {
    try {
        $dockerCheck = (docker info 2>$null)
        if ($LASTEXITCODE -eq 0) { $DockerReady = $true }
    } catch { }

    if (-not $DockerReady) {
        Write-Info "Docker CLI detected, but engine is stopped. Attempting automatic ignition..."
        $DockerReady = Start-DockerEngine
    }
} else {
    $deskPath = Find-DockerDesktopPath
    if ($deskPath) {
        Write-Info "Docker Desktop found at $deskPath. Attempting automatic ignition..."
        $DockerReady = Start-DockerEngine
    }
}

if (-not $DockerReady) {
    Write-Warn "Docker engine is unavailable or could not be ignited automatically."
    Write-Info "Activating Zenith Native Engine (Zero-Failure Fallback)..."
    Start-NativeZenithEngine "Docker is not active. Falling back to Zenith Native Host Mode."
}

$DockerVer = (docker --version)
Write-Ok "$DockerVer active and responsive"

# ── STAGE 3: INSTALLING MISSING DEPENDENCIES ──────────────────────────────────
Write-StageHeader "[3/8] Installing missing dependencies..."

if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
    Ensure-GitInstalled | Out-Null
}
if (-not (Get-Command "python" -ErrorAction SilentlyContinue) -and -not (Get-Command "py" -ErrorAction SilentlyContinue)) {
    Ensure-PythonInstalled | Out-Null
}

$ComposeReady = $false
try {
    $composeCheck = (docker compose version 2>$null)
    if ($LASTEXITCODE -eq 0) { $ComposeReady = $true }
} catch { }

if ($ComposeReady) {
    $cVer = (docker compose version --short 2>$null)
    Write-Ok "Docker Compose plugin ($cVer) detected"
} else {
    Write-Warn "Modern 'docker compose' plugin was not found in Docker CLI."
    Write-Info "Activating Zenith Native Engine (Zero-Failure Fallback)..."
    Start-NativeZenithEngine "Docker Compose plugin is unavailable. Falling back to Zenith Native Host Mode."
}

# ── STAGE 4: VALIDATING ZENITH CONFIGURATION ──────────────────────────────────
Write-StageHeader "[4/8] Validating Zenith configuration..."

# 1. Disk Space check (at least 2GB free)
try {
    $driveLetter = (Get-Item (Get-Location).Path).PSDrive.Name
    $drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
    if ($drive -and $drive.Free) {
        $freeGb = [math]::Round($drive.Free / 1GB, 1)
        if ($freeGb -lt 2.0) {
            Write-Warn "Low disk space: only $freeGb GB available. 2+ GB recommended."
        } else {
            Write-Ok "Disk space: $freeGb GB available"
        }
    }
} catch { }

# 2. Create runtime directories
@("data", "data\memory", "static\screenshots", "$env:TEMP\zenith-files") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
}
Write-Ok "Directory structure verified"

# 3. Sync .env from .env.example preserving existing values
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Ok "Created initial .env configuration from .env.example"
    } else {
        New-Item -ItemType File -Path ".env" | Out-Null
    }
} else {
    if (Test-Path ".env.example") {
        $existingLines = Get-Content ".env" -ErrorAction SilentlyContinue
        if ($null -eq $existingLines) { $existingLines = @() }
        $exampleLines = Get-Content ".env.example" -ErrorAction SilentlyContinue
        if ($null -eq $exampleLines) { $exampleLines = @() }
        $mergedCount = 0
        foreach ($line in $exampleLines) {
            $trimmed = $line.Trim()
            if ($trimmed.StartsWith("#") -or [string]::IsNullOrWhiteSpace($trimmed) -or -not ($trimmed.Contains("="))) { continue }
            $key = $trimmed.Split("=")[0].Trim()
            $found = $existingLines | Where-Object { $_ -and ($_ -match "^\s*$([regex]::Escape($key))\s*=") }
            if (-not $found) {
                Add-Content -Path ".env" -Value $line
                $mergedCount++
            }
        }
        if ($mergedCount -gt 0) {
            Write-Ok "Updated .env: merged $mergedCount configuration keys (existing values preserved)"
        } else {
            Write-Ok ".env configuration verified (all keys up to date)"
        }
    }
}

$TargetPort = Get-TargetPort
$TargetUrl = "http://localhost:$TargetPort"
$HealthUrl = "$TargetUrl/api/health"

# 4. Check Target Port
$PortInUse = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", $TargetPort, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(400, $false)
    if ($success -and $tcp.Connected) {
        $PortInUse = $true
        $tcp.EndConnect($iar)
    }
    $tcp.Close()
} catch { }

if ($PortInUse) {
    try {
        $testResp = Invoke-RestMethod -Uri "$TargetUrl/api/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($testResp.system -eq "Zenith" -or $testResp.status -eq "ok") {
            Write-Ok "Port $TargetPort is already hosting an active Zenith instance."
        } else {
            Write-Warn "Port $TargetPort is occupied by another process on your machine."
        }
    } catch {
        Write-Warn "Port $TargetPort is currently occupied by another process."
    }
} else {
    Write-Ok "Port $TargetPort is available"
}

# 5. Check API Studio Key without leaking secrets
$EnvContent = Get-Content ".env" -ErrorAction SilentlyContinue
$KeyConfigured = $false
foreach ($line in $EnvContent) {
    if ($line -match '^\s*GEMINI_API_KEY\s*=\s*([^#\r\n]+)') {
        $v = $Matches[1].Trim().Trim('"').Trim("'")
        if (-not [string]::IsNullOrWhiteSpace($v) -and $v -ne "your_api_key_here") {
            $KeyConfigured = $true
        }
    }
}

if ($KeyConfigured) {
    Write-Ok "AI Studio key: Configured in .env"
} else {
    Write-Warn "AI Studio key: Not configured in .env"
    Write-Info "Zenith will launch in Setup Mode. You can paste your Gemini key in the web UI."
}

# ── STAGE 5: BUILDING CONTAINERS ──────────────────────────────────────────────
Write-StageHeader "[5/8] Building containers..."

$ImageExists = $false
try {
    $img = (docker images -q zenith:latest 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($img)) { $ImageExists = $true }
} catch { }

if ($Update) {
    Write-Info "Pulling latest repository updates..."
    try { git pull --rebase } catch { Write-Warn "Git pull notice: $_" }
}

if ($ImageExists -and -not $Repair -and -not $Update) {
    Write-Ok "Reusing existing production image zenith:latest (run with -Repair to rebuild)"
} else {
    Write-Info "Building production container image..."
    if ($Repair) {
        docker compose build --no-cache
    } else {
        docker compose build
    }
    Write-Ok "Container compilation completed"
}

# ── STAGE 6: STARTING SERVICES ────────────────────────────────────────────────
Write-StageHeader "[6/8] Starting services..."

# Initialize and start Antigravity Coding Worker on the host
$workerScript = Join-Path $Workspace "scripts\setup-worker.ps1"
if (Test-Path $workerScript) {
    Write-Info "Configuring Antigravity Coding Worker (agy)..."
    try {
        & $workerScript -Action "install-and-start"
    } catch {
        Write-Warn "Antigravity worker startup encountered a warning: $_"
    }
}

$ContainerRunning = $false
try {
    $psOut = (docker compose ps -q --status running zenith 2>$null)
    if (-not [string]::IsNullOrWhiteSpace($psOut)) { $ContainerRunning = $true }
} catch { }

if ($ContainerRunning -and -not $Repair -and -not $Update) {
    Write-Ok "Zenith container (zenith-core) is already active"
} else {
    Write-Info "Launching Zenith containers in detached mode..."
    docker compose up -d
    Write-Ok "Container zenith-core started in background"
}

# ── STAGE 7: WAITING FOR HEALTH CHECKS ────────────────────────────────────────
Write-StageHeader "[7/8] Waiting for health checks..."

$IsHealthy = $false

Write-Host -NoNewline "  "
for ($i = 1; $i -le 40; $i++) {
    try {
        $check = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($check.status -eq "ok" -or $check.system -eq "Zenith") {
            $IsHealthy = $true
            break
        }
    } catch { }
    Write-Host -NoNewline "•"
    Start-Sleep -Milliseconds 1500
}
Write-Host ""

if ($IsHealthy) {
    Write-Ok "Healthcheck verified: Zenith is online and responsive!"
    $tokenFile = Join-Path $env:USERPROFILE ".gemini\antigravity-cli\antigravity-oauth-token"
    if (-not (Test-Path $tokenFile)) {
        Write-Host "`n  💡 First-Time Antigravity Setup:" -ForegroundColor Yellow
        Write-Host "     To enable autonomous coding agents, run 'agy' once in your terminal to sign in with Google.`n" -ForegroundColor DarkGray
    }
} else {
    Write-Err "Zenith did not become healthy in 60 seconds."
    Write-Host "`nDiagnostic logs:" -ForegroundColor Gray
    docker compose logs --tail=25
    Write-Host "`nTroubleshooting:" -ForegroundColor Yellow
    Write-Host "  1. Check full logs:    docker compose logs -f"
    Write-Host "  2. Try repair build:   .\zenith-install.ps1 -Repair"
    Write-Host "  3. Verify port ${TargetPort}:   curl -v http://localhost:$TargetPort/api/health"
    exit 1
}

# ── STAGE 8: OPENING ZENITH ───────────────────────────────────────────────────
Write-StageHeader "[8/8] Opening Zenith..."

$scScript = Join-Path $Workspace "scripts\create-windows-shortcut.ps1"
if (Test-Path $scScript) {
    try { & $scScript } catch { }
}

try {
    Start-Process $TargetUrl
    Write-Ok "Browser window launched to $TargetUrl"
} catch {
    Write-Info "Please open $TargetUrl in your web browser."
}

# Summary Banner
Write-Host "`n╔══════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                                                                          ║" -ForegroundColor Green
Write-Host "║                   ✦  ZENITH IS READY & OPERATIONAL  ✦                   ║" -ForegroundColor Green
Write-Host "║                                                                          ║" -ForegroundColor Green
Write-Host "║   Web Interface:     $TargetUrl                               ║" -ForegroundColor Green
Write-Host "║   Container:         zenith-core                                         ║" -ForegroundColor Green
Write-Host "║   Status:            Healthy (HTTP 200 OK)                               ║" -ForegroundColor Green
Write-Host "║   System Profile:    ~/.zenith/system-info.json                          ║" -ForegroundColor Green
Write-Host "║                                                                          ║" -ForegroundColor Green
Write-Host "║   Useful Commands:                                                       ║" -ForegroundColor Green
Write-Host "║     Stream live logs:   docker compose logs -f                           ║" -ForegroundColor Green
Write-Host "║     Stop Zenith:        docker compose down                              ║" -ForegroundColor Green
Write-Host "║     Restart Zenith:     docker compose restart                           ║" -ForegroundColor Green
Write-Host "║     Update version:     .\zenith-install.ps1 -Update                     ║" -ForegroundColor Green
Write-Host "║     Repair stack:       .\zenith-install.ps1 -Repair                     ║" -ForegroundColor Green
Write-Host "║                                                                          ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════════════════╝`n" -ForegroundColor Green
