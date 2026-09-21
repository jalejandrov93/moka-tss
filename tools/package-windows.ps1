# SPDX-License-Identifier: GPL-3.0-or-later

# Orchestrator script for full Windows package: Python sidecar + Tauri desktop.
# Run from repository root: powershell -ExecutionPolicy Bypass -File tools\package-windows.ps1
# Optional: -SkipSidecar to skip Python sidecar build (requires pre-built sidecar at
# desktop\src-tauri\binaries\moka-sidecar-x86_64-pc-windows-msvc.exe)

param(
    [switch]$SkipSidecar
)

$ErrorActionPreference = "Stop"

function Fail($Message) {
    Write-Error $Message
    exit 1
}

function CheckCommand($Cmd, $Name) {
    try {
        & $Cmd --version 2>$null | Out-Null
        Write-Host "✓ $Name found"
    } catch {
        Fail "$Name not found in PATH. Install $Name and ensure it is on PATH before running this script."
    }
}

# Must run from repository root
if (-not (Test-Path ".\moka-tss.spec")) {
    Fail "moka-tss.spec not found. Run this script from the repository root."
}
if (-not (Test-Path ".\desktop")) {
    Fail "desktop/ directory not found. Run this script from the repository root."
}

Write-Host "=== Checking prerequisites ==="

# Check required tools
CheckCommand "python" "Python 3.13+"
CheckCommand "cargo" "Rust (stable)"
CheckCommand "node" "Node.js 20+"
CheckCommand "npm" "npm"

# Verify Python version
$PyVersion = python --version 2>&1
if (-not $PyVersion) { Fail "Python not found." }
if ($PyVersion -notmatch "Python 3\.(1[3-9]|[2-9]\d)") {
    Write-Host "⚠ Python version: $PyVersion (expected 3.13+)"
}

# Verify Rust
$RustVersion = cargo --version 2>&1
Write-Host "Rust: $RustVersion"

# Verify Node
$NodeVersion = node --version 2>&1
Write-Host "Node: $NodeVersion"

# Verify WebView2 Runtime (Windows only)
if ($IsWindows) {
    $WebView2Path = "${env:ProgramFiles(x86)}\Microsoft\EdgeWebView\Application\*"
    $WebView2SystemPath = "${env:SystemRoot}\System32\msedgewebview2.exe"
    if (-not (Test-Path $WebView2Path) -and -not (Test-Path $WebView2SystemPath)) {
        Write-Host "⚠ WebView2 Runtime not detected. Tauri requires WebView2 (Evergreen Bootstrapper or Fixed Version)."
        Write-Host "  Download: https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    } else {
        Write-Host "✓ WebView2 Runtime found"
    }
}

Write-Host ""
Write-Host "=== Step 1: Build Python sidecar ==="

if (-not $SkipSidecar) {
    Write-Host "Building sidecar via tools\build-sidecar.ps1..."
    & powershell -ExecutionPolicy Bypass -File "tools\build-sidecar.ps1"
    if ($LASTEXITCODE -ne 0) {
        Fail "Sidecar build failed (exit code $LASTEXITCODE)."
    }

    # build-sidecar.ps1 already copies the binary with the Tauri
    # sidecar naming convention; just verify it landed.
    $SidecarDst = ".\desktop\src-tauri\binaries\moka-sidecar-x86_64-pc-windows-msvc.exe"

    if (-not (Test-Path $SidecarDst)) {
        Fail "Sidecar build succeeded but $SidecarDst not found."
    }

    Write-Host "✓ Sidecar ready at $SidecarDst"
} else {
    Write-Host "Skipping sidecar build (--SkipSidecar)."
    $SidecarDst = ".\desktop\src-tauri\binaries\moka-sidecar-x86_64-pc-windows-msvc.exe"
    if (-not (Test-Path $SidecarDst)) {
        Fail "Sidecar binary not found at $SidecarDst. Build it first or run without -SkipSidecar."
    }
    Write-Host "✓ Using existing sidecar at $SidecarDst"
}

Write-Host ""
Write-Host "=== Step 2: Build Tauri desktop (npm install + npm run build) ==="

Push-Location ".\desktop"
try {
    Write-Host "Running npm install..."
    & npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed (exit code $LASTEXITCODE)." }
    
    Write-Host "Running npm run build..."
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail "npm run build failed (exit code $LASTEXITCODE)." }
    
    Write-Host "✓ Desktop frontend built successfully"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Step 3: Build Tauri installer (npx tauri build) ==="

Push-Location ".\desktop"
try {
    Write-Host "Running npx tauri build..."
    & npx tauri build
    if ($LASTEXITCODE -ne 0) { Fail "tauri build failed (exit code $LASTEXITCODE)." }
    
    Write-Host "✓ Tauri build completed"
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "=== Package complete ==="
$InstallerDir = ".\desktop\src-tauri\target\release\bundle"
if (Test-Path $InstallerDir) {
    Get-ChildItem -Path $InstallerDir -Recurse -Filter "*.msi", "*.exe" | ForEach-Object {
        Write-Host "Installer: $($_.FullName)"
    }
} else {
    Write-Host "Installers should be in: $InstallerDir"
    Write-Host "(Check desktop\src-tauri\target\release\bundle\msi\ or \nsis\)"
}