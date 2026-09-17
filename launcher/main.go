package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"unsafe"
)

const (
	zenithVersion = "2.1.0"
	repoURL       = "https://github.com/Aditya-Gamer011/zenith.git"
)

// Windows Console API imports for VT100 / ANSI color and Explorer double-click detection
var (
	kernel32                  = syscall.NewLazyDLL("kernel32.dll")
	procSetConsoleTitleW      = kernel32.NewProc("SetConsoleTitleW")
	procGetConsoleMode        = kernel32.NewProc("GetConsoleMode")
	procSetConsoleMode        = kernel32.NewProc("SetConsoleMode")
	procGetStdHandle          = kernel32.NewProc("GetStdHandle")
	procGetConsoleProcessList = kernel32.NewProc("GetConsoleProcessList")
)

const (
	stdOutputHandle                 = uint32(0xFFFFFFF5) // -11
	enableVirtualTerminalProcessing = uint32(0x0004)
)

func initConsole() {
	// Set console title
	title, _ := syscall.UTF16PtrFromString(fmt.Sprintf("Zenith Cognitive Operating Layer v%s", zenithVersion))
	procSetConsoleTitleW.Call(uintptr(unsafe.Pointer(title)))

	// Enable Virtual Terminal Processing for ANSI colors
	hOut, _, _ := procGetStdHandle.Call(uintptr(stdOutputHandle))
	if hOut != 0 && hOut != uintptr(syscall.InvalidHandle) {
		var mode uint32
		r, _, _ := procGetConsoleMode.Call(hOut, uintptr(unsafe.Pointer(&mode)))
		if r != 0 {
			mode |= enableVirtualTerminalProcessing
			procSetConsoleMode.Call(hOut, uintptr(mode))
		}
	}
}

// isLaunchedFromExplorer checks if the process was started by double-clicking in Explorer
func isLaunchedFromExplorer() bool {
	var processList [2]uint32
	r, _, _ := procGetConsoleProcessList.Call(
		uintptr(unsafe.Pointer(&processList[0])),
		uintptr(len(processList)),
	)
	// If only 1 process is attached to this console, it was spawned in a fresh console window
	return r <= 1
}

func pauseIfDoubleClicked(isExplorer bool, exitCode int) {
	if isExplorer || exitCode != 0 {
		fmt.Println()
		fmt.Print("Press Enter to exit...")
		var b [1]byte
		os.Stdin.Read(b[:])
	}
}

func findScriptPath() (string, string, error) {
	// 1. Check directory of current executable
	exePath, err := os.Executable()
	if err == nil {
		exeDir := filepath.Dir(exePath)
		candidate := filepath.Join(exeDir, "zenith-install.ps1")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, exeDir, nil
		}
		candidateScripts := filepath.Join(exeDir, "scripts", "zenith-install.ps1")
		if _, err := os.Stat(candidateScripts); err == nil {
			return candidateScripts, exeDir, nil
		}
		// Check parent directory
		parentDir := filepath.Dir(exeDir)
		candidateParent := filepath.Join(parentDir, "zenith-install.ps1")
		if _, err := os.Stat(candidateParent); err == nil {
			return candidateParent, parentDir, nil
		}
	}

	// 2. Check current working directory
	cwd, err := os.Getwd()
	if err == nil {
		candidate := filepath.Join(cwd, "zenith-install.ps1")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, cwd, nil
		}
	}

	// 3. Check %USERPROFILE%\.zenith\app
	homeDir, err := os.UserHomeDir()
	if err == nil {
		appDir := filepath.Join(homeDir, ".zenith", "app")
		candidate := filepath.Join(appDir, "zenith-install.ps1")
		if _, err := os.Stat(candidate); err == nil {
			return candidate, appDir, nil
		}

		// 4. Auto-clone if missing
		fmt.Println("[Zenith] Repository not found locally. Cloning to ~/.zenith/app...")
		os.MkdirAll(filepath.Join(homeDir, ".zenith"), 0755)
		gitPath, err := exec.LookPath("git")
		if err != nil {
			return "", "", fmt.Errorf("git is required to clone Zenith. Please install git or place zenith.exe in the zenith repository folder")
		}

		cloneCmd := exec.Command(gitPath, "clone", "--depth", "1", repoURL, appDir)
		cloneCmd.Stdout = os.Stdout
		cloneCmd.Stderr = os.Stderr
		if err := cloneCmd.Run(); err != nil {
			return "", "", fmt.Errorf("failed to clone repository: %v", err)
		}
		if _, err := os.Stat(candidate); err == nil {
			return candidate, appDir, nil
		}
	}

	return "", "", fmt.Errorf("could not locate zenith-install.ps1")
}

func findPowerShell() (string, error) {
	// Try pwsh.exe (PowerShell Core 7+) first
	if p, err := exec.LookPath("pwsh.exe"); err == nil {
		return p, nil
	}
	if p, err := exec.LookPath("pwsh"); err == nil {
		return p, nil
	}
	// Fall back to built-in Windows PowerShell
	if p, err := exec.LookPath("powershell.exe"); err == nil {
		return p, nil
	}
	if p, err := exec.LookPath("powershell"); err == nil {
		return p, nil
	}

	// Standard system32 fallback
	sysRoot := os.Getenv("SystemRoot")
	if sysRoot == "" {
		sysRoot = `C:\Windows`
	}
	standardPS := filepath.Join(sysRoot, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
	if _, err := os.Stat(standardPS); err == nil {
		return standardPS, nil
	}

	return "", fmt.Errorf("neither PowerShell (powershell.exe) nor PowerShell Core (pwsh.exe) could be found on this system")
}

func mapArgs(args []string) []string {
	var mapped []string
	for _, arg := range args {
		switch strings.ToLower(arg) {
		case "--repair", "-repair":
			mapped = append(mapped, "-Repair")
		case "--update", "-update":
			mapped = append(mapped, "-Update")
		case "--uninstall", "-uninstall":
			mapped = append(mapped, "-Uninstall")
		case "--stop", "-stop":
			mapped = append(mapped, "-Stop")
		case "--restart", "-restart":
			mapped = append(mapped, "-Restart")
		case "--logs", "-logs":
			mapped = append(mapped, "-Logs")
		case "--status", "-status":
			mapped = append(mapped, "-Status")
		case "--yes", "-yes", "-y", "/y":
			mapped = append(mapped, "-Yes")
		case "--help", "-help", "-h", "/h", "/?":
			mapped = append(mapped, "-?")
		default:
			mapped = append(mapped, arg)
		}
	}
	return mapped
}

func main() {
	initConsole()
	isExplorer := isLaunchedFromExplorer()

	scriptPath, workDir, err := findScriptPath()
	if err != nil {
		fmt.Fprintf(os.Stderr, "\n[Zenith Error] %v\n", err)
		pauseIfDoubleClicked(isExplorer, 1)
		os.Exit(1)
	}

	psPath, err := findPowerShell()
	if err != nil {
		fmt.Fprintf(os.Stderr, "\n[Zenith Error] %v\n", err)
		pauseIfDoubleClicked(isExplorer, 1)
		os.Exit(1)
	}

	// Build PowerShell invocation
	psArgs := []string{
		"-NoProfile",
		"-ExecutionPolicy", "Bypass",
		"-File", scriptPath,
	}
	rawArgs := os.Args[1:]
	if isExplorer && len(rawArgs) == 0 {
		psArgs = append(psArgs, "-Yes")
	} else {
		psArgs = append(psArgs, mapArgs(rawArgs)...)
	}

	cmd := exec.Command(psPath, psArgs...)
	cmd.Dir = workDir
	cmd.Stdin = os.Stdin
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr

	runErr := cmd.Run()

	exitCode := 0
	if runErr != nil {
		if exitErr, ok := runErr.(*exec.ExitError); ok {
			exitCode = exitErr.ExitCode()
		} else {
			exitCode = 1
			fmt.Fprintf(os.Stderr, "\n[Zenith Launcher] Execution failed: %v\n", runErr)
		}
	}

	pauseIfDoubleClicked(isExplorer, exitCode)
	os.Exit(exitCode)
}
