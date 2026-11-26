# FeatherOS

**FeatherOS** is a lightweight, bootable x86_64 operating system built on **Debian Minimal** (`amd64` + `i386` multiarch) with a familiar Windows-like desktop (**FeatherShell**) and seamless `.exe` / `.msi` compatibility (**FeatherRun**).

## Highlights

- **Ultra-lightweight (~250–400 MB idle RAM):** Debian Minimal + Openbox + Tint2 Windows-style taskbar + `jgmenu` searchable Start Menu + `zram` zstd compressed swap.
- **Seamless Windows software (`feather-run`):** Double-click `.exe` and `.msi` files directly in File Explorer. Pure-Python PE/MSI inspection, isolated per-app Wine/Proton Bottles, automatic Start Menu `.lnk` shortcut sync, and automatic **Vulkan → WineD3D fallback** so apps work both on bare-metal GPUs and inside QEMU/VirtualBox VMs.
- **Compatibility Manager GUI (`feather-compat`):** Manage bottles, switch Windows version (`win11`–`winxp`), toggle DXVK/VKD3D-Proton, GameMode, MangoHud, Virtual Desktops, install common runtimes (`vcrun2022`, `dotnet48`, `corefonts`, `d3dx9`), and switch system profiles.
- **Welcome & Curated App Hub (`feather-store`):** One-click installation for Browsers (Firefox ESR, Chromium), Gaming (Steam + Proton, Lutris, GE-Proton, GameMode/MangoHud), Productivity (LibreOffice, VLC, GIMP), and Developer tools.
- **Graphical Hard-Drive Installer (`Calamares`):** Included in the Live ISO so you can test FeatherOS live and install it permanently to any SSD/HDD with UEFI + BIOS GRUB support.
- **Performance Profiles (`feather-ctl`):** Switch between **Balanced**, **Low-RAM Saver** (2–4 GB PCs), and **Gaming Performance**.
- **Reproducible Hybrid UEFI + BIOS ISO:** Boots in QEMU, VirtualBox, or flashed onto a USB stick for real hardware.

---

## Project Layout

```text
featheros/
├── config/featheros.conf        # OS identity, Debian suite, zram & ISO settings
├── compat/featheros/            # FeatherRun CLI, PE inspector, Bottles, Shortcuts, GUI, System Control
├── desktop/overlay/             # FeatherShell rootfs overlay (Openbox, Tint2, jgmenu, MIME, LightDM, Plymouth)
├── build/                       # Debian debootstrap + SquashFS + hybrid UEFI/BIOS ISO builder & Dockerfile
├── scripts/                     # QEMU boot launchers (Windows & Linux), host check, build validator
├── .github/workflows/           # Cloud CI test & bootable ISO builder
└── tests/                       # Automated unit, overlay, and build pipeline tests
```

---

## Try FeatherRun & FeatherCompat Right Now (Windows or Linux)

Run the full test & build validation suite (Python 3.10+, zero external deps):

```powershell
python -m unittest discover -s tests -t . -v
python scripts\validate-build.py
```

Preview the Compatibility Manager or FeatherStore Welcome App Hub right on Windows (uses the dark Tkinter preview automatically when GTK3 isn't present):

```powershell
$env:PYTHONPATH = "compat"
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

## Building the Bootable ISO (`featheros-0.1.0-amd64.iso`)

### Option 1: Cloud Build via GitHub Actions (Recommended on Windows — zero local Linux setup)
1. Push this repository to GitHub.
2. Open **Actions → FeatherOS CI & ISO Builder → Run workflow**.
3. Download the `featheros-live-iso` artifact (`featheros-0.1.0-amd64.iso` + `.sha256`).

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

On Windows, check host readiness or install QEMU via `winget`:
```powershell
.\scripts\setup-windows-host.ps1
.\scripts\setup-windows-host.ps1 -InstallQemu
```

Boot the ISO with 2 GB RAM (to test low-RAM responsiveness):
```powershell
.\scripts\run-qemu.ps1 -IsoPath .\dist\featheros-0.1.0-amd64.iso -RamMB 2048 -Cpus 2
```

Live credentials: user `feather`, password `feather` (auto-logs in with passwordless `sudo`).
