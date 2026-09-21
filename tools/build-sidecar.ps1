# SPDX-License-Identifier: GPL-3.0-or-later

# Build script for the MOKA TSS sidecar Windows executable (Tauri integration).
#
# PREREQUISITES:
# 1. OS: Windows (x86_64). This script cannot run on Linux or macOS because it
#    invokes the Windows Python interpreter and PyInstaller to create Windows binaries.
# 2. Python: Python 3.10+ (e.g. C:\Python313\python.exe, Python 3.11, 3.12, or the py launcher)
#    must be installed and accessible in PATH, or pre-configured in .venv or venv.
# 3. Execution Policy: Run from the repository root on Windows with:
#    powershell -ExecutionPolicy Bypass -File tools\build-sidecar.ps1
#
# OUTCOME:
# Freezes moka.py into a single-file console executable (moka-sidecar.exe) via PyInstaller,
# and copies it to desktop\src-tauri\binaries\moka-sidecar-x86_64-pc-windows-msvc.exe
# adhering to Tauri's externalBin naming convention.

$ErrorActionPreference = "Stop"

function Fail($Message) {
    # Fail loudly: print a useful message and exit non-zero immediately
    # instead of letting later steps run on a broken state.
    Write-Error $Message
    exit 1
}

# Must run from the repository root, where moka-sidecar.spec lives.
if (-not (Test-Path ".\moka-sidecar.spec")) {
    Fail "moka-sidecar.spec not found. Run this script from the repository root."
}

# Locate existing virtualenv or create .venv if missing.
$VenvPython = $null
if (Test-Path ".\.venv\Scripts\python.exe") {
    $VenvPython = ".\.venv\Scripts\python.exe"
} elseif (Test-Path ".\venv\Scripts\python.exe") {
    $VenvPython = ".\venv\Scripts\python.exe"
} else {
    Write-Host "Virtual environment not found. Creating .venv..."
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command "python" -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        Fail "Python interpreter not found in PATH. Please install Python 3 (or the py launcher) and add it to PATH."
    }

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path ".\.venv\Scripts\python.exe")) {
        Fail "Failed to create virtual environment in .\.venv (exit code $LASTEXITCODE)."
    }
    $VenvPython = ".\.venv\Scripts\python.exe"
}

Write-Host "Using Python interpreter: $VenvPython"

Write-Host "Installing requirements and PyInstaller..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (exit code $LASTEXITCODE)." }
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "'pip install -r requirements.txt' failed (exit code $LASTEXITCODE)." }
& $VenvPython -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { Fail "'pip install pyinstaller' failed (exit code $LASTEXITCODE)." }

Write-Host "Running PyInstaller for moka-sidecar.spec..."
& $VenvPython -m PyInstaller --noconfirm moka-sidecar.spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (exit code $LASTEXITCODE). See the output above." }

$DistExe = ".\dist\moka-sidecar.exe"
if (-not (Test-Path $DistExe)) {
    Fail "Build finished but $DistExe is missing. Check the PyInstaller output above."
}

$TargetDir = ".\desktop\src-tauri\binaries"
if (-not (Test-Path $TargetDir)) {
    Write-Host "Creating Tauri binaries directory: $TargetDir"
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
}

$TargetExe = Join-Path $TargetDir "moka-sidecar-x86_64-pc-windows-msvc.exe"
Write-Host "Copying $DistExe to $TargetExe..."
Copy-Item -Path $DistExe -Destination $TargetExe -Force
if (-not (Test-Path $TargetExe)) {
    Fail "Failed to copy sidecar binary to $TargetExe."
}

Write-Host "Sidecar build OK: $TargetExe"
Write-Host "Tauri sidecar binary is ready."
