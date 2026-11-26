#!/usr/bin/env python3
"""Static and structural validator for FeatherOS ISO build pipeline and overlays."""

from __future__ import annotations

import configparser
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent

LINUX_LF_PATHS = [
    REPO_ROOT / "config",
    REPO_ROOT / "build",
    REPO_ROOT / "desktop" / "overlay",
    REPO_ROOT / ".github" / "workflows",
    REPO_ROOT / "scripts" / "run-qemu.sh",
]

REQUIRED_REPO_FILES = [
    "config/featheros.conf",
    "pyproject.toml",
    "build/packages-core.list",
    "build/packages-optional.list",
    "build/chroot-setup.sh",
    "build/build-iso.sh",
    "build/Dockerfile",
    ".github/workflows/build-iso.yml",
    "scripts/run-qemu.ps1",
    "scripts/run-qemu.sh",
    "scripts/setup-windows-host.ps1",
    "compat/featheros/pe_inspector.py",
    "compat/featheros/system_probe.py",
    "compat/featheros/bottles.py",
    "compat/featheros/shortcuts.py",
    "compat/featheros/cli.py",
    "compat/featheros/runners.py",
    "compat/featheros/ctl.py",
    "compat/featheros/compat_gui.py",
    "compat/featheros/store.py",
    "compat/featheros/settings_hub.py",
    "compat/featheros/fluent_theme.py",
    "compat/featheros/selftest.py",
    "desktop/overlay/usr/share/themes/FeatherWin11-Dark/gtk-3.0/gtk.css",
    "desktop/overlay/usr/share/themes/FeatherWin11-Dark/xfwm4/themerc",
    "desktop/overlay/usr/share/themes/FeatherWin11-Light/gtk-3.0/gtk.css",
    "desktop/overlay/usr/share/themes/FeatherWin11-Light/xfwm4/themerc",
    "desktop/overlay/usr/share/backgrounds/featheros/wallpaper.svg",
    "desktop/overlay/usr/share/backgrounds/featheros/wallpaper-light.svg",
    "desktop/overlay/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml",
    "desktop/overlay/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml",
    "desktop/overlay/etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml",
    "desktop/overlay/etc/xdg/menus/applications-merged/feather-windows.menu",
    "desktop/overlay/etc/xdg/autostart/feather-polkit.desktop",
    "desktop/overlay/etc/xdg/autostart/feather-clipman.desktop",
    "desktop/overlay/usr/local/bin/feather-firstboot",
    "desktop/overlay/usr/local/bin/feather-polkit-agent",
    "desktop/overlay/usr/local/bin/feather-calamares",
    "desktop/overlay/usr/local/bin/feather-boot-report",
    "desktop/overlay/etc/systemd/system/feather-boot-report.service",
    "desktop/overlay/etc/calamares/settings.conf",
    "desktop/overlay/etc/calamares/modules/unpackfs.conf",
    "desktop/overlay/etc/calamares/modules/bootloader.conf",
    "desktop/overlay/etc/calamares/modules/removeuser.conf",
    "desktop/overlay/etc/calamares/modules/packages.conf",
    "desktop/overlay/etc/calamares/modules/shellprocess.conf",
    "desktop/overlay/etc/calamares/branding/featheros/branding.desc",
    "desktop/overlay/etc/calamares/branding/featheros/show.qml",
]

FORBIDDEN_LEGACY_PATHS = [
    "desktop/overlay/etc/xdg/openbox",
    "desktop/overlay/etc/xdg/tint2",
    "desktop/overlay/etc/xdg/jgmenu",
    "desktop/overlay/etc/xdg/featheros",
    "desktop/overlay/etc/skel/.config/pcmanfm",
    "desktop/overlay/usr/share/themes/FeatherDark",
    "desktop/overlay/usr/share/file-manager",
]

PKG_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+(:[a-z0-9]+)?$")


def check_required_files() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_REPO_FILES:
        if not (REPO_ROOT / rel).is_file():
            errors.append(f"Missing required project file: {rel}")
    for rel in FORBIDDEN_LEGACY_PATHS:
        if (REPO_ROOT / rel).exists():
            errors.append(f"Obsolete v0.1 legacy overlay path still exists: {rel}")
    return errors


def check_lf_endings() -> list[str]:
    errors: list[str] = []
    for root in LINUX_LF_PATHS:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for p in paths:
            if p.is_file() and b"\r\n" in p.read_bytes():
                errors.append(f"CRLF detected in Linux file: {p.relative_to(REPO_ROOT)}")
    return errors


def check_package_lists() -> list[str]:
    errors: list[str] = []
    seen_all: set[str] = set()
    seen_core: set[str] = set()
    for list_name in ("packages-core.list", "packages-optional.list"):
        path = REPO_ROOT / "build" / list_name
        seen_local: set[str] = set()
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not PKG_TOKEN_RE.match(line):
                errors.append(f"Invalid Debian package name '{line}' at {list_name}:{lineno}")
            if line in seen_local:
                errors.append(f"Duplicate package '{line}' in {list_name}:{lineno}")
            if line in seen_all:
                errors.append(f"Package '{line}' duplicated across core & optional lists")
            seen_local.add(line)
            seen_all.add(line)
            if list_name == "packages-core.list":
                seen_core.add(line)

    # Critical packages sanity check (must be in core so Live ISO & Calamares never miss them)
    for must_have in (
        "linux-image-amd64",
        "live-boot",
        "grub-pc-bin",
        "grub-efi-amd64-bin",
        "efibootmgr",
        "ntfs-3g",
        "mate-polkit",
        "xfwm4",
        "xfce4-panel",
        "thunar",
        "wine",
        "wine32:i386",
        "zram-tools",
        "fonts-inter",
        "libnotify-bin",
    ):
        if must_have not in seen_core:
            errors.append(f"Critical package missing from packages-core.list: {must_have}")
    return errors


def check_xml_and_desktop() -> list[str]:
    errors: list[str] = []
    overlay = REPO_ROOT / "desktop" / "overlay"
    for xml_file in list(overlay.rglob("*.xml")) + list(overlay.rglob("*.svg")) + list(overlay.rglob("*.menu")):
        try:
            ET.parse(xml_file)
        except ET.ParseError as exc:
            errors.append(f"XML parse error in {xml_file.relative_to(REPO_ROOT)}: {exc}")

    for df in overlay.rglob("*.desktop"):
        text = df.read_text(encoding="utf-8")
        if "lxterminal" in text:
            errors.append(f"Obsolete 'lxterminal' reference in {df.relative_to(REPO_ROOT)}")
        if "sh -c" in text and "read -p" in text:
            errors.append(f"POSIX sh/dash incompatible 'read -p' in {df.relative_to(REPO_ROOT)}")
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(df, encoding="utf-8")
            if "Desktop Entry" not in cp:
                errors.append(f"Missing [Desktop Entry] in {df.relative_to(REPO_ROOT)}")
        except configparser.Error as exc:
            errors.append(f"Invalid .desktop file {df.relative_to(REPO_ROOT)}: {exc}")

    uca = overlay / "etc" / "skel" / ".config" / "Thunar" / "uca.xml"
    if uca.is_file():
        uca_text = uca.read_text(encoding="utf-8")
        if "sh -c" in uca_text and "read -p" in uca_text:
            errors.append("POSIX sh/dash incompatible 'read -p' in Thunar/uca.xml")
    return errors


def check_version_and_build_safety() -> list[str]:
    errors: list[str] = []
    conf = (REPO_ROOT / "config" / "featheros.conf").read_text(encoding="utf-8")
    m = re.search(r'^OS_VERSION="([^"]+)"', conf, re.MULTILINE)
    if not m:
        return ["Could not parse OS_VERSION from config/featheros.conf"]
    ver = m.group(1)

    checks = [
        ("pyproject.toml", f'version = "{ver}"'),
        ("compat/featheros/__init__.py", f'__version__ = "{ver}"'),
        ("desktop/overlay/etc/featheros-release", f'VERSION_ID="{ver}"'),
        ("desktop/overlay/etc/issue", f"FeatherOS {ver}"),
        ("desktop/overlay/etc/calamares/branding/featheros/branding.desc", f"version: {ver}"),
    ]
    for rel, needle in checks:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if needle not in text:
            errors.append(f"Version drift in {rel}: expected '{needle}'")

    build_iso = (REPO_ROOT / "build" / "build-iso.sh").read_text(encoding="utf-8")
    if re.search(r"mksquashfs[\s\S]{0,200}-e\s+boot(?:\s|\\|$)", build_iso):
        errors.append("build/build-iso.sh must NOT pass '-e boot' to mksquashfs (breaks Calamares installs)")
    return errors


def main() -> int:
    all_errors = (
        check_required_files()
        + check_lf_endings()
        + check_package_lists()
        + check_xml_and_desktop()
        + check_version_and_build_safety()
    )
    if all_errors:
        print("FeatherOS build validation FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("FeatherOS build validation PASSED:")
    print(f"  - Required project files verified ({len(REQUIRED_REPO_FILES)} files, 0 legacy paths)")
    print("  - Linux build, overlay, and CI scripts use strict LF line endings")
    print("  - Debian core & optional package lists validated (XFCE 4.20 + Wine/i386 + GRUB2 + Polkit)")
    print("  - XML, SVG, .menu, and .desktop overlay definitions validated")
    print("  - Version consistency and Calamares /boot preservation verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
