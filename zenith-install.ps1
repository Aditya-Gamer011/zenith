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
        if (-not (Test-Path $dest)) {
            Write-Info "Cloning Zenith repository into $dest..."
            git clone --depth 1 $RepoUrl $dest
        }
        Set-Location $dest
        return $dest
    }
}

Show-Banner
$Workspace = Resolve-Workspace
Write-Info "Working directory: $Workspace"

# Quick mode handlers
if ($Stop) {
    Write-StageHeader "Stopping Zenith services..."
    docker compose down
    Write-Ok "Zenith stopped."
    exit 0
}
if ($Restart) {
    Write-StageHeader "Restarting Zenith services..."
    docker compose restart
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
    Write-Host "`nHealthcheck (/api/health):" -ForegroundColor Gray
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8005/api/health" -TimeoutSec 3
        $resp | ConvertTo-Json -Depth 3
        Write-Ok "Zenith is online and responding."
    } catch {
        Write-Warn "Zenith is not responding on port 8005."
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

$GpuName = if ($GpuInfo) { ($GpuInfo | Select-Object -First 1).Name } else { "None / Integrated" }
$GpuAvailable = ($GpuName -ne "None / Integrated")
$GpuIsNvidia = ($GpuName -match "NVIDIA")

$MemClass = if ($TotalRamMb -lt 2048) { "low" } elseif ($TotalRamMb -lt 8192) { "standard" } else { "high" }
$RecommendedWorkers = if ($TotalRamMb -lt 2048) { 1 } else { 2 }

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
        default_port = $DefaultPort
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

$DockerInstalled = (Get-Command "docker" -ErrorAction SilentlyContinue) -ne $null

if (-not $DockerInstalled) {
    Write-Warn "Docker is not installed on this host."
    Write-Host "  Zenith requires Docker Desktop (with WSL2 engine) on Windows for secure containerization."
    if (Prompt-Confirm "Install Docker Desktop via winget now?" "y") {
        Write-Info "Executing winget install Docker.DockerDesktop..."
        winget install -e --id Docker.DockerDesktop --accept-source-agreements --accept-package-agreements
        Write-Ok "Docker Desktop installer triggered. Please complete setup and restart your terminal."
        exit 0
    } else {
        Write-Err "Docker installation declined. Zenith cannot run without Docker."
        exit 1
    }
}

# Verify Docker daemon is running
$DockerReady = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { $DockerReady = $true }
} catch { }

if (-not $DockerReady) {
    Write-Warn "Docker Desktop is installed but the engine is not responding."
    Write-Info "Please ensure Docker Desktop is launched and the engine has finished starting."
    exit 1
}

$DockerVer = (docker --version)
Write-Ok "$DockerVer active and responsive"

# ── STAGE 3: INSTALLING MISSING DEPENDENCIES ──────────────────────────────────
Write-StageHeader "[3/8] Installing missing dependencies..."

$ComposeReady = $false
try {
    $null = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) { $ComposeReady = $true }
} catch { }

if ($ComposeReady) {
    $cVer = (docker compose version --short 2>$null)
    Write-Ok "Docker Compose plugin ($cVer) detected"
} else {
    Write-Err "Modern 'docker compose' plugin was not found in Docker CLI."
    Write-Info "Please update Docker Desktop to version 4.x or higher to enable Compose v2."
    exit 1
}

# ── STAGE 4: VALIDATING ZENITH CONFIGURATION ──────────────────────────────────
Write-StageHeader "[4/8] Validating Zenith configuration..."

# Create runtime directories
@("data", "data\memory", "static\screenshots", "$env:TEMP\zenith-files") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
}
Write-Ok "Directory structure verified"

# Check Port 8005
$PortInUse = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $iar = $tcp.BeginConnect("127.0.0.1", 8005, $null, $null)
    $success = $iar.AsyncWaitHandle.WaitOne(400, $false)
    if ($success -and $tcp.Connected) {
        $PortInUse = $true
        $tcp.EndConnect($iar)
    }
    $tcp.Close()
} catch { }

if ($PortInUse) {
    try {
        $testResp = Invoke-RestMethod -Uri "http://localhost:8005/api/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($testResp.system -eq "Zenith") {
            Write-Ok "Port 8005 is already hosting an active Zenith instance."
        } else {
            Write-Warn "Port 8005 is occupied by another process on your machine."
        }
    } catch {
        Write-Warn "Port 8005 is currently occupied by another process."
    }
} else {
    Write-Ok "Port 8005 is available"
}

# Sync .env from .env.example preserving existing values
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Ok "Created initial .env configuration from .env.example"
    } else {
        New-Item -ItemType File -Path ".env" | Out-Null
    }
} else {
    if (Test-Path ".env.example") {
        $existingLines = Get-Content ".env"
        $exampleLines = Get-Content ".env.example"
        $mergedCount = 0
        foreach ($line in $exampleLines) {
            $trimmed = $line.Trim()
            if ($trimmed.StartsWith("#") -or [string]::IsNullOrWhiteSpace($trimmed)) { continue }
            $key = $trimmed.Split("=")[0].Trim()
            $found = $existingLines | Where-Object { $_.Trim().StartsWith("$key=") }
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

# Check API Studio Key without leaking secrets
$EnvContent = Get-Content ".env" -ErrorAction SilentlyContinue
$KeyConfigured = $false
foreach ($line in $EnvContent) {
    if ($line -match '^\s*GEMINI_API_KEY=(.+)$') {
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
    $img = docker images -q zenith:latest 2>&1
    if (-not [string]::IsNullOrWhiteSpace($img)) { $ImageExists = $true }
} catch { }

if ($Update) {
    Write-Info "Pulling latest repository updates..."
    git pull --rebase
}

if ($ImageExists -and -not $Repair -and -not $Update) {
    Write-Ok "Reusing existing production image zenith:latest (run with -Repair to rebuild)"
} else {
    Write-Info "Building production container image..."
    $buildArg = if ($Repair) { "--no-cache" } else { "" }
    if ($Repair) {
        docker compose build --no-cache
    } else {
        docker compose build
    }
    Write-Ok "Container compilation completed"
}

# ── STAGE 6: STARTING SERVICES ────────────────────────────────────────────────
Write-StageHeader "[6/8] Starting services..."

$ContainerRunning = $false
try {
    $psOut = docker compose ps -q zenith 2>&1
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

$TargetUrl = "http://localhost:8005"
$HealthUrl = "$TargetUrl/api/health"
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
} else {
    Write-Err "Zenith did not become healthy in 60 seconds."
    Write-Host "`nDiagnostic logs:" -ForegroundColor Gray
    docker compose logs --tail=25
    exit 1
}

# ── STAGE 8: OPENING ZENITH ───────────────────────────────────────────────────
Write-StageHeader "[8/8] Opening Zenith..."

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
Write-Host "║   Web Interface:     http://localhost:8005                               ║" -ForegroundColor Green
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
