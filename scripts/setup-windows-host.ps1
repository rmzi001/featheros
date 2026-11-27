<#
.SYNOPSIS
    Inspect Windows host readiness for building and boot-testing FeatherOS.
.PARAMETER InstallQemu
    Install QEMU via winget for local ISO boot testing.
#>
param(
    [switch]$InstallQemu
)

$ErrorActionPreference = "Stop"

Write-Host "=== FeatherOS Windows Host Readiness ===" -ForegroundColor Cyan

$FreeGB = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
$HasQemu = [bool](Get-Command qemu-system-x86_64 -ErrorAction SilentlyContinue) -or (Test-Path "C:\Program Files\qemu\qemu-system-x86_64.exe")
$HasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)
$HasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
$HasGit = [bool](Get-Command git -ErrorAction SilentlyContinue)
$HasPython = [bool](Get-Command python -ErrorAction SilentlyContinue)

$WslDistros = & wsl -l -q 2>$null
$HasWslDistro = ($LASTEXITCODE -eq 0) -and ($WslDistros -and ($WslDistros -join "").Trim().Length -gt 0)

[PSCustomObject]@{
    FreeDiskC_GB  = $FreeGB
    Python        = $HasPython
    Git           = $HasGit
    Winget        = $HasWinget
    QEMU          = $HasQemu
    WSL2_Distro   = $HasWslDistro
    Docker        = $HasDocker
} | Format-List

if ($InstallQemu) {
    if ($HasQemu) {
        Write-Host "QEMU is already installed." -ForegroundColor Green
    } elseif ($HasWinget) {
        Write-Host "Installing QEMU via winget..." -ForegroundColor Yellow
        winget install -e --id SoftwareFreedomConservancy.QEMU
    } else {
        Write-Error "winget is unavailable. Download QEMU manually from https://www.qemu.org/download/#windows"
        exit 1
    }
}

Write-Host "Next steps to build your FeatherOS ISO:" -ForegroundColor Cyan
Write-Host "  Option A (Cloud / zero local disk pressure): Push this repo to GitHub and run 'FeatherOS CI & ISO Builder' workflow."
Write-Host "  Option B (Local WSL2 Debian): Run 'wsl --install -d Debian' in an Admin terminal, reboot, then run 'sudo ./build/build-iso.sh'."
Write-Host "  Boot test ISO in VM: .\scripts\run-qemu.ps1 -IsoPath .\dist\featheros-0.4.0-amd64.iso"
