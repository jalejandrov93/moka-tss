# SPDX-License-Identifier: GPL-3.0-or-later

# Build script for the MOKA TSS Windows executable.
# Run from the repository root on Windows:  powershell -ExecutionPolicy Bypass -File tools\build-moka-tss.ps1
# Expects a virtualenv in .\venv or .\.venv (created with C:\Python313\python.exe -m venv .venv).
# This script cannot run on Linux or macOS: it invokes the Windows venv
# interpreter and PyInstaller, which must execute on the target platform.

$ErrorActionPreference = "Stop"

function Fail($Message) {
    # Fail loudly: print a useful message and exit non-zero immediately
    # instead of letting later steps run on a broken state.
    Write-Error $Message
    exit 1
}

# Must run from the repository root, where moka-tss.spec lives.
if (-not (Test-Path ".\moka-tss.spec")) {
    Fail "moka-tss.spec not found. Run this script from the repository root."
}

$VenvPython = if (Test-Path ".\.venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
} elseif (Test-Path ".\venv\Scripts\python.exe") {
    ".\venv\Scripts\python.exe"
} else {
    Fail "Venv not found at .\venv or .\.venv. Create it first, e.g.: C:\Python313\python.exe -m venv .venv"
}

Write-Host "Installing requirements..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { Fail "pip upgrade failed (exit code $LASTEXITCODE)." }
& $VenvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "'pip install -r requirements.txt' failed (exit code $LASTEXITCODE)." }

Write-Host "Running PyInstaller..."
& $VenvPython -m PyInstaller --noconfirm moka-tss.spec
if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed (exit code $LASTEXITCODE). See the output above." }

$ExePath = ".\dist\moka\moka.exe"
if (-not (Test-Path $ExePath)) {
    Fail "Build finished but $ExePath is missing. Check the PyInstaller output above."
}

Write-Host "Build OK: $ExePath"
Write-Host "Double-click it (Python not required on the target machine)."
