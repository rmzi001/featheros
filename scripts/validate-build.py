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
    "desktop/overlay/etc/calamares/settings.conf",
    "desktop/overlay/etc/calamares/modules/unpackfs.conf",
    "desktop/overlay/etc/calamares/modules/bootloader.conf",
    "desktop/overlay/etc/calamares/branding/featheros/branding.desc",
]

PKG_TOKEN_RE = re.compile(r"^[a-z0-9][a-z0-9+.\-]+(:[a-z0-9]+)?$")


def check_required_files() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_REPO_FILES:
        if not (REPO_ROOT / rel).is_file():
            errors.append(f"Missing required project file: {rel}")
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
    # Critical packages sanity check
    for must_have in ("linux-image-amd64", "live-boot", "openbox", "wine", "wine32:i386", "zram-tools"):
        if must_have not in seen_all:
            errors.append(f"Critical package missing from package lists: {must_have}")
    return errors


def check_xml_and_desktop() -> list[str]:
    errors: list[str] = []
    overlay = REPO_ROOT / "desktop" / "overlay"
    for xml_file in list(overlay.rglob("*.xml")) + list(overlay.rglob("*.svg")):
        try:
            ET.parse(xml_file)
        except ET.ParseError as exc:
            errors.append(f"XML parse error in {xml_file.relative_to(REPO_ROOT)}: {exc}")

    for df in overlay.rglob("*.desktop"):
        cp = configparser.ConfigParser(interpolation=None)
        try:
            cp.read(df, encoding="utf-8")
            if "Desktop Entry" not in cp:
                errors.append(f"Missing [Desktop Entry] in {df.relative_to(REPO_ROOT)}")
        except configparser.Error as exc:
            errors.append(f"Invalid .desktop file {df.relative_to(REPO_ROOT)}: {exc}")
    return errors


def main() -> int:
    all_errors = (
        check_required_files()
        + check_lf_endings()
        + check_package_lists()
        + check_xml_and_desktop()
    )
    if all_errors:
        print("FeatherOS build validation FAILED:", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("FeatherOS build validation PASSED:")
    print(f"  - Required project files verified ({len(REQUIRED_REPO_FILES)} files)")
    print("  - Linux build, overlay, and CI scripts use strict LF line endings")
    print("  - Debian package lists validated (amd64 + i386 multiarch + FeatherShell + Wine)")
    print("  - XML, SVG, and .desktop overlay definitions validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
