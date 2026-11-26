<#
.SYNOPSIS
    Boot the FeatherOS Live ISO inside QEMU on Windows.
.EXAMPLE
    .\scripts\run-qemu.ps1
    .\scripts\run-qemu.ps1 -IsoPath .\dist\featheros-0.1.0-amd64.iso -RamMB 4096 -Cpus 4
#>
param(
    [string]$IsoPath = "",
    [int]$RamMB = 2048,
    [int]$Cpus = 2,
    [string]$DiskPath = "",
    [int]$CreateDiskGB = 0,
    [switch]$DisableAccel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not $IsoPath) {
    $IsoPath = Join-Path $RepoRoot "dist\featheros-0.1.0-amd64.iso"
}

if (-not (Test-Path $IsoPath)) {
    Write-Error "FeatherOS ISO not found at '$IsoPath'. Build it via GitHub Actions, WSL2, or Docker first."
    exit 1
}

$QemuBin = Get-Command "qemu-system-x86_64.exe" -ErrorAction SilentlyContinue
$QemuExe = if ($QemuBin) { $QemuBin.Source } elseif (Test-Path "C:\Program Files\qemu\qemu-system-x86_64.exe") { "C:\Program Files\qemu\qemu-system-x86_64.exe" } else { $null }

if (-not $QemuExe) {
    Write-Error "QEMU not found. Run '.\scripts\setup-windows-host.ps1 -InstallQemu' or install via winget."
    exit 1
}

$QemuDir = Split-Path -Parent $QemuExe
$QemuImg = Join-Path $QemuDir "qemu-img.exe"

if ($CreateDiskGB -gt 0) {
    if (-not $DiskPath) {
        $DiskPath = Join-Path $RepoRoot "dist\featheros-disk.qcow2"
    }
    if (-not (Test-Path $DiskPath)) {
        Write-Host "Creating ${CreateDiskGB}GB persistent virtual disk at $DiskPath..."
        & $QemuImg create -f qcow2 $DiskPath "${CreateDiskGB}G"
    }
}

$ArgsList = @(
    "-m", "$RamMB",
    "-smp", "$Cpus",
    "-cdrom", "$IsoPath",
    "-boot", "d",
    "-vga", "virtio",
    "-display", "sdl,gl=off",
    "-netdev", "user,id=net0",
    "-device", "virtio-net-pci,netdev=net0",
    "-usb",
    "-device", "usb-tablet"
)

$VirtEnabled = $false
try {
    $VirtEnabled = [bool](Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty VirtualizationFirmwareEnabled)
} catch {
    $VirtEnabled = $false
}

if (-not $DisableAccel -and $VirtEnabled) {
    $ArgsList += @("-accel", "whpx", "-accel", "tcg")
} else {
    if (-not $DisableAccel -and -not $VirtEnabled) {
        Write-Host "Note: BIOS virtualization (VT-x/AMD-V) is off; launching in QEMU TCG mode." -ForegroundColor Yellow
    }
    $ArgsList += @("-accel", "tcg")
}

if ($DiskPath -and (Test-Path $DiskPath)) {
    $ArgsList += @("-drive", "file=$DiskPath,format=qcow2,if=virtio")
}

Write-Host "Launching FeatherOS in QEMU (${RamMB} MB RAM, ${Cpus} vCPUs)..."
Write-Host "ISO: $IsoPath"
& $QemuExe @ArgsList
