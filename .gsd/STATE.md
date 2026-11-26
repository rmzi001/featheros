# FeatherOS — Session State

**Status:** v0.2.0 (Plume Fluent) Released & Empirically Boot-Verified
**SPEC Status:** FINALIZED
**Last Updated:** 2026-11-26

## Published Release (`v0.2.0`)
- **GitHub Repository:** https://github.com/rmzi001/featheros
- **GitHub Release (`v0.2.0`):** https://github.com/rmzi001/featheros/releases/tag/v0.2.0
- **Bootable ISO:** `featheros-0.2.0-amd64.iso` (1,595.74 MB / ~1.56 GiB, hybrid UEFI + Legacy BIOS + Rufus `/EFI/BOOT`)
- **SHA256:** `a2987c565a98740227213beedde94d2bc06571b2c6c5ca1819e45e6097320157`
- **CI Run #5 (100% green):** https://github.com/rmzi001/featheros/actions/runs/45821222621

## Major Upgrades Shipped in v0.2.0
- Upgraded desktop from minimal Openbox/Tint2 to **Windows 11 Dark Glass on XFCE 4.20** (~350–420 MB idle RAM)
- Centered frosted dark taskbar (`xfce4-panel`) + custom cyan 4-pane Start button (`featheros-start.svg`) + rounded Whisker Start Menu
- Custom `FeatherWin11-Dark` GTK3 theme + `Arc-Dark` window borders + `Papirus-Dark` icons + Dark Bloom SVG wallpaper
- New Windows-style unified **System Settings Hub** (`feather-settings`) covering System, Network, Bluetooth & Devices, Personalization, Sound, Windows Apps, and Updates
- Complete built-in app suite: tabbed Thunar File Explorer (`Windows Drive (C:)` sidebar + `.exe`/`.msi` right-click actions), Firefox ESR, Live Task Manager (`Ctrl+Shift+Esc`), Snipping Tool (`Super+Shift+S`), Calculator, Media/PDF/Photo/Editor/Archive apps, Bluetooth, Volume, Power, Notification Center
- Boot tuning: disabled slow live background timers (`apt-daily`, `man-db`, `fstrim`), eliminated `/etc/network` init warning, branded `/etc/issue` as `FeatherOS 0.2.0 (Plume Fluent)`
