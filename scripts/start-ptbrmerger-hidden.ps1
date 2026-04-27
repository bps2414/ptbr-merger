$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$stdoutPath = Join-Path $root "debug_stdout.txt"
$stderrPath = Join-Path $root "debug_stderr.txt"

function Write-LaunchError {
    param([string] $Message)

    $Message | Set-Content -Path $stderrPath -Encoding UTF8
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shell.Popup($Message, 12, "PTBRMerger", 0x10) | Out-Null
    } catch {
        # If Windows Script Host is unavailable, the debug file still carries the error.
    }
}

function Test-Command {
    param([string] $Command)

    $null -ne (Get-Command $Command -ErrorAction SilentlyContinue)
}

function Test-LocalServer {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $connection = $client.BeginConnect("127.0.0.1", 8787, $null, $null)
        if (-not $connection.AsyncWaitHandle.WaitOne(500)) {
            return $false
        }
        $client.EndConnect($connection)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

if (Test-LocalServer) {
    Start-Process "http://127.0.0.1:8787"
    exit 0
}

$pythonExe = $null
$pythonArgs = @("-m", "src.web.server")
$venvPython = Join-Path $root ".venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} elseif (Test-Command "py.exe") {
    $pythonExe = "py.exe"
    $pythonArgs = @("-3") + $pythonArgs
} elseif (Test-Command "python.exe") {
    $pythonExe = "python.exe"
}

if (-not $pythonExe) {
    Write-LaunchError "Python nao encontrado. Instale Python 3.11+ ou desative o alias da Microsoft Store para python.exe."
    exit 1
}

"" | Set-Content -Path $stdoutPath -Encoding UTF8
"" | Set-Content -Path $stderrPath -Encoding UTF8

Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $pythonArgs `
    -WorkingDirectory $root `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath
