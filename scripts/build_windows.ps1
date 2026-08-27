<#
.SYNOPSIS
Build CloudIPResolver.exe locally on Windows.

.DESCRIPTION
This script installs the development/build dependencies into the currently
selected Python environment, runs the test suite (unless -SkipTests is used),
then asks PyInstaller to create a one-file, windowed executable.

PyInstaller is not a cross-compiler, so this script intentionally refuses to
build on non-Windows systems. The finished executable is written to
dist\CloudIPResolver.exe.
#>

[CmdletBinding()]
param(
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# PSScriptRoot is the scripts directory. Resolve the repository root so the
# command works regardless of the caller's current directory.
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SpecFile = Join-Path $RepoRoot "CloudIPResolver.spec"
$ExePath = Join-Path $RepoRoot "dist\CloudIPResolver.exe"

if ($env:OS -ne "Windows_NT") {
    throw "CloudIPResolver.exe must be built on Windows. PyInstaller is not a cross-compiler."
}

Push-Location $RepoRoot
try {
    if (-not $env:VIRTUAL_ENV) {
        Write-Warning "No Python virtual environment appears to be active."
    }

    Write-Host "Installing/updating development and build dependencies..."
    python -m pip install -e ".[dev]"
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed."
    }

    if (-not $SkipTests) {
        Write-Host "Running tests before packaging..."
        python -m pytest
        if ($LASTEXITCODE -ne 0) {
            throw "Tests failed. The executable was not built."
        }
    }

    Write-Host "Building one-file Windows GUI executable..."
    python -m PyInstaller --noconfirm --clean $SpecFile
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }

    if (-not (Test-Path $ExePath -PathType Leaf)) {
        throw "PyInstaller completed but $ExePath was not created."
    }

    $Exe = Get-Item $ExePath
    $SizeMb = [math]::Round($Exe.Length / 1MB, 2)

    Write-Host ""
    Write-Host "Build complete."
    Write-Host "Executable: $($Exe.FullName)"
    Write-Host "Size: $SizeMb MB"
    Write-Host ""
    Write-Host "Next: double-click CloudIPResolver.exe and run a real AWS/Azure/GCP test."
}
finally {
    Pop-Location
}
