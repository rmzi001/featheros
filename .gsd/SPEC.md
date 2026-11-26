# FeatherOS — System Specification

**Status:** FINALIZED
**Version:** 0.1.0-alpha
**Target Architecture:** x86_64 (with `i386` multiarch for 32-bit Win32/gaming compatibility)

---

## 1. Vision & Goals

**FeatherOS** is a lightweight, bootable x86_64 operating system built on a minimal Debian Linux core that runs Windows software (`.exe` / `.msi` desktop apps, legacy Win32 utilities, developer tools, and DirectX games) as first-class citizens without Windows background bloat.

### Core Targets
| Metric | Target |
|---|---|
| Cold desktop idle RAM | 250–400 MB |
| Live ISO image size | ~1.2–1.8 GB (zstd SquashFS) |
| Minimum hardware | 64-bit x86 CPU, 2 GB RAM (4 GB+ recommended for games), 8 GB disk/USB |
| Boot modes | Hybrid UEFI + Legacy BIOS (QEMU, VirtualBox, bare-metal USB) |
| Windows software UX | Double-click `.exe`/`.msi`, per-app isolated bottles, Start Menu shortcuts, GUI Compatibility Manager |

---

## 2. System Architecture

### 2.1 Core OS Layer (`base/`)
- **Base distribution:** Debian Minimal (`trixie` default, configurable via `config/featheros.conf`) with `amd64` + `i386` multiarch enabled.
- **Kernel & Hardware:** Standard Debian Linux kernel + non-free hardware firmware (`firmware-linux`, Wi-Fi, Ethernet, AMD/Intel/Mesa Vulkan & OpenGL drivers).
- **Memory & Services:**
  - `zram-tools` (zstd compressed swap in RAM) for low-RAM machines.
  - PipeWire + WirePlumber for low-latency audio.
  - NetworkManager for Wi-Fi/Ethernet management.
  - Minimal systemd footprint (no snapd, no background telemetry/indexing).
- **Boot & Live System:** `live-boot` + hybrid GRUB2 (UEFI) / ISOLINUX (BIOS) built via `debootstrap` + `mksquashfs` + `xorriso`, with Plymouth FeatherOS splash screen and auto-login live session.

### 2.2 Desktop Layer — FeatherShell (`desktop/`)
- **Window Manager:** Openbox (X11, ~15 MB RAM) for maximum compatibility with legacy Win32 windows, installers, system tray icons, and DirectX games.
- **Compositor:** Picom (lightweight, toggleable off in Low-RAM / Gaming mode).
- **Taskbar & Start Menu:** Tint2 bottom taskbar + `jgmenu` Windows-style Start Menu with search, pinned apps, Windows app entries, quick `C:\` access, and power controls.
- **File Manager & Desktop:** PCManFM with desktop icons, Windows drive shortcuts, and right-click context actions for `.exe`/`.msi` files.
- **Display Manager:** LightDM with custom FeatherOS branding.
- **Included Minimal Apps:** Terminal, text editor, archive manager, image viewer, task manager, web browser installer/launcher.

### 2.3 Windows Compatibility Layer — FeatherRun (`compat/`)
Built as a modular, tested Python + GTK3 suite with clean CLI and GUI separation:

1. **PE Binary Inspector (`featheros/pe_inspector.py`)**
   - Pure-Python PE/COFF header parser (`MZ`/`PE\0\0`).
   - Detects architecture (`x86` 32-bit vs `x64` 64-bit), subsystem (`GUI` vs `CUI` console), and installer heuristics (NSIS, Inno Setup, MSI, InstallShield).

2. **Bottle & Prefix Manager (`featheros/bottles.py`)**
   - Manages isolated Wine/Proton prefixes under `~/.local/share/featheros/bottles/<name>` plus a fast default shared bottle.
   - Persists per-bottle JSON config: Windows version (`win11`, `win10`, `win7`, `winxp`), architecture (`win64`/`win32`), DXVK/VKD3D toggles, Esync/Fsync, Virtual Desktop resolution, DPI scaling, DLL overrides, custom runner path, and environment variables.
   - Automatically detects Vulkan capability and falls back cleanly to OpenGL/WineD3D in VMs without GPU passthrough (e.g., QEMU software rendering).

3. **Seamless Launcher & MIME Handler (`feather-run`)**
   - Registered as default handler for `.exe` and `.msi` via XDG MIME + `.desktop` files.
   - Double-clicking an `.exe`/`.msi` inspects the binary, resolves or creates the right bottle, configures graphics translation, launches the app, and scans for newly installed Windows shortcuts to sync into the FeatherShell Start Menu.

4. **Compatibility Manager GUI (`feather-compat`)**
   - Lightweight GTK3 GUI to launch/install `.exe`/`.msi` files, manage bottles, toggle DXVK/VKD3D/Virtual Desktop/Windows version, install common runtimes (`vcrun2022`, `dotnet48`, `corefonts` via `winetricks`), and open a Gaming Hub (Steam + Proton + GE-Proton runner downloader).

5. **System Control Center (`feather-ctl`)**
   - Switch profiles: **Balanced**, **Low-RAM** (disables compositor, lowers swappiness), and **Gaming** (enables gamemode, performance governor).
   - Live diagnostics: RAM usage, GPU & Vulkan readiness, 32-bit Wine/multiarch status.

### 2.4 Build, CI & Test Pipeline (`build/`, `scripts/`, `.github/workflows/`, `tests/`)
- **Reproducible Linux ISO Builder (`build/build-iso.sh`):** Builds rootfs with `debootstrap`, installs FeatherShell + FeatherRun `.deb`/overlay files, compresses SquashFS, and generates bootable hybrid `featheros-0.1.0-amd64.iso`.
- **Container Build (`build/Dockerfile`):** Reproducible Debian builder environment for Docker or WSL2.
- **GitHub Actions ISO Pipeline (`.github/workflows/build-iso.yml`):** Builds the bootable `.iso` in cloud Linux runners and publishes it as a downloadable artifact (zero local Linux setup required).
- **VM Boot Harness (`scripts/run-qemu.ps1`, `scripts/run-qemu.sh`):** One-command QEMU launch with UEFI/BIOS, networking, audio, and optional persistent virtual disk.
- **Host Helper (`scripts/setup-windows-host.ps1`):** Checks/installs QEMU and guides optional WSL2 setup on Windows.
- **Automated Test Suite (`tests/`):** Python `pytest`/`unittest` suite testing PE inspection, bottle lifecycle, environment/Vulkan fallback, shortcut syncing, CLI commands, and build config integrity.

---

## 3. Known Limitations (Honest Scope)
- **Kernel-level anti-cheat** (Vanguard, FACEIT, EA Javelin, etc.) and **Windows kernel drivers** (`.sys`) cannot run on a Linux kernel.
- **DRM-locked apps** (e.g., latest Adobe Creative Cloud / Microsoft 365 desktop suite) have partial or limited compatibility under Wine; lightweight/open alternatives or older/portable versions work well.
- **Building the ISO locally on Windows** requires WSL2 or Docker (Linux chroot + `mksquashfs` + `xorriso`). Without WSL2/Docker locally, the ISO can be built via GitHub Actions or after enabling WSL2.

---

## 4. Planned Delivery Phases
1. **Phase 1 — Project Scaffold & Core FeatherRun Engine:** Repo structure, PE inspector, Bottle/Prefix manager, Vulkan auto-fallback, Start Menu shortcut syncer, `feather-run` CLI, and full unit/integration tests.
2. **Phase 2 — FeatherRun GUI & System Control (`feather-compat`, `feather-ctl`):** GTK3 Compatibility Manager, `.exe`/`.msi` install flow, Gaming Hub runner helper, and performance profile controller.
3. **Phase 3 — FeatherShell Desktop Environment:** Openbox, Tint2, `jgmenu` Windows-style Start Menu, PCManFM `.exe` integration, GTK/icon theme, LightDM, Plymouth splash, wallpaper, and system overlay.
4. **Phase 4 — Reproducible ISO Build Pipeline & VM Boot Harness:** `debootstrap` + `xorriso` live ISO builder, Dockerfile, GitHub Actions workflow, QEMU launch scripts, and end-to-end validation.

---

## 5. Approval Gate
Approve this specification to mark `Status: FINALIZED` and begin Phase 1.
