# FeatherOS — Session State

**Status:** v0.1.0 (Plume) Released & Empirically Boot-Verified
**SPEC Status:** FINALIZED
**Last Updated:** 2026-11-26

## Published Release
- **GitHub Repository:** https://github.com/rmzi001/featheros
- **GitHub Release (`v0.1.0`):** https://github.com/rmzi001/featheros/releases/tag/v0.1.0
- **Bootable ISO:** `featheros-0.1.0-amd64.iso` (1,444.26 MB / ~1.41 GiB, hybrid UEFI + Legacy BIOS + Rufus `/EFI/BOOT` tree)
- **SHA256:** `22e1b5fcf79f43eb609f15cac709b259818da54f9fe93120bb1a48e7f7d27d19`
- **CI Run #4 (100% green):** https://github.com/rmzi001/featheros/actions/runs/45781090020

## Empirical Verification Captured
- **Python unit, overlay & build pipeline tests:** 28/28 passed locally and on GitHub Actions (`ubuntu-latest`)
- **Static build & LF validator (`scripts/validate-build.py`):** PASSED
- **Live KVM QEMU boot-test:** Booted cleanly from BIOS GRUB -> Linux kernel -> systemd (`zramswap`, `NetworkManager`, `lightdm.service`) -> Openbox FeatherDark + Tint2 Windows-style taskbar + PCManFM wallpaper + Calamares Desktop icon + GTK3 Welcome App Hub (`feather-store`) in under 21 seconds.
- **Visual proof:** Live QEMU desktop screenshot (`boot-desktop.png`, 71.5 KB) verified.
