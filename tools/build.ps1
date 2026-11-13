<#
.SYNOPSIS
    Builds Ghostpad: runs the tests, compiles the executable, and creates a
    portable zip and an installer wizard.

.DESCRIPTION
    Outputs (all in dist\):
      dist\Ghostpad\Ghostpad.exe                 app folder (run in place)
      dist\Ghostpad-<version>-portable.zip       copy to any PC, unzip, run
      dist\installer\Ghostpad-Setup-<version>.exe installer wizard (needs Inno Setup 6)

.PARAMETER SkipTests
    Skip the unit tests.

.PARAMETER SkipInstaller
    Skip the installer step even if Inno Setup is available.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\build.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Step([string]$Name, [scriptblock]$Action) {
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)." }
}

# Single source of truth for the version: __version__ in ghostpad.pyw.
$version = (Select-String -Path 'ghostpad.pyw' -Pattern '__version__ = "([^"]+)"').Matches[0].Groups[1].Value
Write-Host "Building Ghostpad $version" -ForegroundColor Green

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found on PATH. Install Python 3.10+ from https://www.python.org/downloads/.'
}

if (-not $SkipTests) {
    Invoke-Step 'Running tests' { python -m unittest discover -s tests }
}

Invoke-Step 'Checking PyInstaller' { python -m PyInstaller --version | Out-Null }
Invoke-Step 'Building executable' { python -m PyInstaller --noconfirm --clean Ghostpad.spec }
Remove-Item -Recurse -Force 'build' -ErrorAction SilentlyContinue

$zip = "dist\Ghostpad-$version-portable.zip"
Write-Host "==> Creating portable zip" -ForegroundColor Cyan
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path 'dist\Ghostpad' -DestinationPath $zip

$installer = $null
if (-not $SkipInstaller) {
    $iscc = @(
        (Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue).Source,
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1

    if ($iscc) {
        Invoke-Step 'Building installer' { & $iscc /Q "/DAppVersion=$version" 'installer\ghostpad.iss' }
        $installer = "dist\installer\Ghostpad-Setup-$version.exe"
    } else {
        Write-Warning 'Inno Setup 6 not found; skipped the installer. Install it with: winget install JRSoftware.InnoSetup'
    }
}

Write-Host ''
Write-Host 'Build complete:' -ForegroundColor Green
Write-Host "  App folder : dist\Ghostpad\Ghostpad.exe"
Write-Host "  Portable   : $zip"
if ($installer) { Write-Host "  Installer  : $installer" }
