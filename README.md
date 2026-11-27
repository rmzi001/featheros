# FeatherOS v0.4.0 (`Plume Wholesome`)

**FeatherOS** is a lightweight, bootable x86_64 operating system built on **Debian Minimal** (`amd64` + `i386` multiarch) with a modern **Windows 11 Dark & Light Glass** desktop (**FeatherShell on XFCE 4.20**) and seamless `.exe` / `.msi` compatibility (**FeatherRun**).

## Highlights

- **Modern Windows 11 Dark & Light Glass Desktop (`XFCE 4.20`):** Centered translucent taskbar, searchable Whisker Start Menu (`Win`), custom Fluent Dark & Light XFWM4 window borders, `Inter` system typography, `Win+E` File Explorer, `Win+I` Settings, `Win+V` Clipboard History, `Win+L` Lock Screen, `Win+Shift+S` Snipping Tool, and `Alt+Tab` live window previews.
- **Lightweight Efficiency (~400–550 MB idle RAM):** Debian Minimal (`--no-install-recommends`) + `zram` zstd compressed swap + performance profiles (**Balanced**, **Low-RAM Saver**, **Gaming Performance**).
- **Seamless Windows Software (`feather-run` & `feather-compat`):** Double-click `.exe` and `.msi` files directly in File Explorer. Pure-Python PE/MSI inspection (with ARM64 guard), isolated per-app Wine/Proton Bottles, real `winecfg`/DPI/DXVK configuration, automatic Start Menu `.lnk` sync under **Windows Apps**, 32-bit PipeWire audio (`libpulse0:i386` + `libasound2-plugins:i386`), and automatic **Vulkan → WineD3D fallback**.
- **Unified Windows-Style Settings Hub (`feather-settings`):** Instant Dark/Light Glass theme switching, Display, Network, Bluetooth, Sound, Power, Performance Profiles, Windows Apps, Default Apps, Startup Apps, System Info, and Updates — all searchable from one window.
- **FeatherStore Welcome & Curated App Hub (`feather-store`):** One-click install for Browsers (Firefox ESR, Chromium), Gaming (Steam + Proton, Lutris, live GE-Proton downloader, GameMode/MangoHud), Productivity (LibreOffice, VLC, GIMP), and Developer tools.
- **Bootable Calamares Disk Installer:** UEFI + Legacy BIOS GRUB2 (`grub-pc-bin`, `grub-efi-amd64-bin`, `efibootmgr`), NTFS/exFAT support (`ntfs-3g`, `exfatprogs`), Polkit GUI elevation (`mate-polkit`), live-user cleanup (`removeuser`, `packages`, `shellprocess`), and QML slideshow.
- **Built-in QA Checking Agent (`feather-selftest`):** Empirical 100-point in-OS health & Win32 execution verifier that runs automatically on every CI KVM boot.

---

## Project Layout

```text
featheros/
├── config/featheros.conf        # OS identity (v0.3.0), Debian suite, zram & ISO settings
├── compat/featheros/            # FeatherRun, Bottles, Runners, Shortcuts, Settings Hub, Store, Selftest
├── desktop/overlay/             # FeatherShell v0.3 overlay (XFCE 4.20, Dark/Light Glass themes, Calamares, Polkit)
├── build/                       # Debian debootstrap + SquashFS + hybrid UEFI/BIOS ISO builder & Dockerfile
├── scripts/                     # QEMU launchers, browser VNC console, host check, build validator
├── .github/workflows/           # Cloud CI test, KVM QEMU ISO boot verification & Release publisher
└── tests/                       # Automated unit, selftest, overlay, and build pipeline tests
```

---

## Try FeatherRun, FeatherSettings & FeatherSelftest Locally

Run the full test & build validation suite (Python 3.10+, zero external deps):

```powershell
python -m unittest discover -s tests -t . -v
python scripts\validate-build.py
```

Preview FeatherSettings, FeatherCompat, or FeatherStore on Windows (uses the dark Tkinter preview automatically when GTK3 isn't present):

```powershell
$env:PYTHONPATH = "compat"
python -m featheros.settings_hub
python -m featheros.compat_gui
python -m featheros.store
```

Test `feather-run` inspection & dry-run bottle launch planning on any Windows `.exe`:

```powershell
$env:PYTHONPATH = "compat"
python -m featheros.cli inspect C:\Windows\notepad.exe
python -m featheros.cli --isolated --dry-run C:\Windows\notepad.exe
python -m featheros.ctl status
```

---

## Building the Bootable ISO (`featheros-0.4.0-amd64.iso`)

### Option 1: Cloud Build via GitHub Actions (Recommended on Windows)
1. Push to GitHub or open **Actions → FeatherOS CI & ISO Builder → Run workflow**.
2. Download the verified ISO, SHA256, live KVM screenshots, and `feather-selftest` report from **Releases**.

### Option 2: Local Build in WSL2 (Debian/Ubuntu) or Native Linux
```bash
sudo apt-get update
sudo apt-get install -y debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin grub-common mtools dosfstools
sudo ./build/build-iso.sh
```

### Option 3: Local Build in Docker
```bash
docker build -t featheros-builder -f build/Dockerfile .
docker run --rm --privileged -v "$(pwd):/workspace" featheros-builder
```

---

## Boot-Testing in QEMU

```powershell
.\scripts\run-qemu.ps1 -IsoPath .\dist\featheros-0.4.0-amd64.iso -RamMB 2048 -Cpus 2
```

Live credentials: user `feather`, password `feather` (auto-logs in with passwordless `sudo`).
