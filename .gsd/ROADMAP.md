# FeatherOS — Roadmap

## Phase 1: Project Scaffold & Core FeatherRun Engine — COMPLETE (`279a80f`)
- [x] Repo configuration (`pyproject.toml`, `config/featheros.conf`, `.gitattributes`, `.gitignore`)
- [x] Pure-Python PE/MSI binary inspector (`pe_inspector.py`)
- [x] System & graphics/Vulkan readiness probe (`system_probe.py`)
- [x] Bottle/Prefix manager with automatic Vulkan-to-WineD3D fallback (`bottles.py`)
- [x] MS-SHLLINK `.lnk` parser & XDG Start Menu shortcut syncer (`shortcuts.py`)
- [x] `feather-run` CLI & MIME dispatcher (`cli.py`)
- [x] Automated unit & integration tests (`tests/test_featherrun_core.py`)

## Phase 2: FeatherRun GUI & System Control — COMPLETE (`98d18d0`)
- [x] Compatibility Manager controller & GTK3/Tkinter GUI (`compat_gui.py`, `feather-compat`)
- [x] Gaming Hub runner catalog & safe GE-Proton extractor (`runners.py`)
- [x] Performance profile & diagnostics controller (`ctl.py`, `feather-ctl`)
- [x] Unit tests (`tests/test_compat_and_ctl.py`)

## Phase 3: FeatherShell Desktop Environment — COMPLETE (`d6fff31`)
- [x] OS identity (`/etc/featheros-release`) & kernel/Esync/zram tuning
- [x] Openbox window manager config + FeatherDark theme
- [x] Tint2 Windows-style taskbar + `jgmenu` searchable Start Menu
- [x] PCManFM file manager config, `.exe`/`.msi` MIME & context actions, GTK3 dark theme
- [x] Custom FeatherOS SVG wallpaper, LightDM config, Plymouth boot splash
- [x] Overlay & config validation tests (`tests/test_overlay_and_configs.py`)

## Phase 4: Reproducible ISO Build Pipeline, CI & VM Harness — COMPLETE
- [x] Curated minimal Debian package lists (`build/packages-core.list`, `build/packages-optional.list`)
- [x] Chroot provisioner (`build/chroot-setup.sh`) & hybrid UEFI/BIOS ISO builder (`build/build-iso.sh`)
- [x] Reproducible container builder (`build/Dockerfile`)
- [x] GitHub Actions cloud ISO build workflow (`.github/workflows/build-iso.yml`)
- [x] QEMU launch scripts (`scripts/run-qemu.ps1`, `scripts/run-qemu.sh`) & Windows host setup helper (`scripts/setup-windows-host.ps1`)
- [x] Static validator (`scripts/validate-build.py`) & full verification suite (`tests/test_build_pipeline.py`)

## Phase 5: FeatherStore Welcome Hub & Calamares Installer — COMPLETE (`f9eb5de`)
- [x] Curated FeatherStore Welcome & App Hub (`compat/featheros/store.py`, GTK3 + Tkinter preview)
- [x] Calamares graphical hard-drive installer configs (`desktop/overlay/etc/calamares/`)
- [x] `lxpolkit` GUI elevation support + first-boot desktop installer shortcut
- [x] Live GUI screenshots verified & dark theme contrast polished (`28/28` tests passing)
