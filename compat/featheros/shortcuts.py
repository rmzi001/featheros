"""Windows Start Menu (.lnk / Program Files) discovery and XDG .desktop sync.

Allows newly installed Windows software inside any FeatherOS bottle to appear
automatically in the FeatherShell Start Menu and launch via `feather-run`.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import struct
from typing import Iterable

from .bottles import BottleManager, slugify

LNK_HEADER_SIZE = 0x4C
LNK_CLSID = bytes.fromhex("0114020000000000c000000000000046")

# LinkFlags bitmask (MS-SHLLINK 2.1.1)
HAS_LINK_TARGET_ID_LIST = 0x00000001
HAS_LINK_INFO = 0x00000002
HAS_NAME = 0x00000004
HAS_RELATIVE_PATH = 0x00000008
HAS_WORKING_DIR = 0x00000010
HAS_ARGUMENTS = 0x00000020
IS_UNICODE = 0x00000080

IGNORED_EXE_KEYWORDS = (
    "unins",
    "uninstall",
    "crashreport",
    "crashhandler",
    "update",
    "updater",
    "helper",
    "redist",
    "vc_redist",
    "dxsetup",
)


@dataclass(frozen=True)
class WindowsShortcut:
    """Discovered Windows application inside a FeatherOS bottle."""

    name: str
    bottle_slug: str
    target_path: Path
    source_kind: str  # "lnk" or "program_files"
    arguments: str = ""


def _read_counted_string(data: bytes, offset: int, is_unicode: bool) -> tuple[str, int]:
    if offset + 2 > len(data):
        return "", len(data)
    char_count = struct.unpack_from("<H", data, offset)[0]
    offset += 2
    byte_len = char_count * 2 if is_unicode else char_count
    raw = data[offset : offset + byte_len]
    text = raw.decode("utf-16-le" if is_unicode else "latin-1", errors="ignore")
    return text, offset + byte_len


def _read_null_terminated(data: bytes, offset: int) -> str:
    end = data.find(b"\x00", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("latin-1", errors="ignore")


def parse_lnk_target(lnk_path: str | Path) -> tuple[str | None, str]:
    """Parse an MS-SHLLINK (.lnk) file and return (windows_target_path, arguments)."""
    data = Path(lnk_path).read_bytes()
    if len(data) < LNK_HEADER_SIZE:
        return None, ""

    header_size = struct.unpack_from("<I", data, 0)[0]
    clsid = data[4:20]
    if header_size != LNK_HEADER_SIZE or clsid != LNK_CLSID:
        return None, ""

    flags = struct.unpack_from("<I", data, 20)[0]
    is_unicode = bool(flags & IS_UNICODE)
    offset = LNK_HEADER_SIZE

    if flags & HAS_LINK_TARGET_ID_LIST:
        if offset + 2 > len(data):
            return None, ""
        id_list_size = struct.unpack_from("<H", data, offset)[0]
        offset += 2 + id_list_size

    local_base_path: str | None = None
    if flags & HAS_LINK_INFO:
        if offset + 4 <= len(data):
            info_size = struct.unpack_from("<I", data, offset)[0]
            if info_size >= 28 and offset + info_size <= len(data):
                info_flags = struct.unpack_from("<I", data, offset + 8)[0]
                if info_flags & 0x00000001:  # VolumeIDAndLocalBasePath
                    local_base_off = struct.unpack_from("<I", data, offset + 16)[0]
                    common_suffix_off = struct.unpack_from("<I", data, offset + 24)[0]
                    base = _read_null_terminated(data, offset + local_base_off)
                    suffix = _read_null_terminated(data, offset + common_suffix_off)
                    local_base_path = base + suffix if suffix else base
            offset += info_size

    relative_path: str | None = None
    arguments = ""

    if flags & HAS_NAME:
        _, offset = _read_counted_string(data, offset, is_unicode)
    if flags & HAS_RELATIVE_PATH:
        relative_path, offset = _read_counted_string(data, offset, is_unicode)
    if flags & HAS_WORKING_DIR:
        _, offset = _read_counted_string(data, offset, is_unicode)
    if flags & HAS_ARGUMENTS:
        arguments, offset = _read_counted_string(data, offset, is_unicode)

    return local_base_path or relative_path, arguments.strip()


def windows_path_to_prefix_path(win_path: str, prefix_dir: Path) -> Path | None:
    """Convert a Windows C:\\... path into a path inside prefix_dir/drive_c."""
    normalized = win_path.strip().strip('"').replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        drive = normalized[0].lower()
        rest = normalized[2:].lstrip("/")
        if drive == "c":
            return prefix_dir / "drive_c" / rest
        return prefix_dir / "dosdevices" / f"{drive}:" / rest
    return None


def _is_ignored_exe(exe_path: Path) -> bool:
    stem = exe_path.stem.lower()
    return any(keyword in stem for keyword in IGNORED_EXE_KEYWORDS)


def discover_bottle_shortcuts(manager: BottleManager, slug: str) -> list[WindowsShortcut]:
    """Find launchable Windows apps inside a bottle via Start Menu .lnk files and Program Files."""
    prefix = manager.prefix_dir(slug)
    drive_c = prefix / "drive_c"
    if not drive_c.is_dir():
        return []

    found: dict[Path, WindowsShortcut] = {}

    # 1. Scan Start Menu and Desktop .lnk files first (cleanest human-facing names)
    lnk_roots = [
        drive_c / "ProgramData" / "Microsoft" / "Windows" / "Start Menu",
    ]
    users_dir = drive_c / "users"
    if users_dir.is_dir():
        for user_dir in users_dir.iterdir():
            if user_dir.is_dir():
                lnk_roots.append(user_dir / "Desktop")
                lnk_roots.append(
                    user_dir / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu"
                )

    for root in lnk_roots:
        if not root.is_dir():
            continue
        for lnk in sorted(root.rglob("*.lnk")):
            raw_target, args = parse_lnk_target(lnk)
            if not raw_target:
                continue
            resolved = windows_path_to_prefix_path(raw_target, prefix)
            if resolved and resolved.suffix.lower() == ".exe" and resolved.is_file():
                if _is_ignored_exe(resolved):
                    continue
                found[resolved.resolve()] = WindowsShortcut(
                    name=lnk.stem,
                    bottle_slug=slug,
                    target_path=resolved.resolve(),
                    source_kind="lnk",
                    arguments=args,
                )

    # 2. Discover primary executables inside Program Files / Program Files (x86)
    for pf_name in ("Program Files", "Program Files (x86)"):
        pf_dir = drive_c / pf_name
        if not pf_dir.is_dir():
            continue
        for app_dir in sorted(pf_dir.iterdir()):
            if not app_dir.is_dir():
                continue
            for exe in sorted(app_dir.glob("*.exe")):
                resolved = exe.resolve()
                if resolved in found or _is_ignored_exe(exe):
                    continue
                found[resolved] = WindowsShortcut(
                    name=exe.stem,
                    bottle_slug=slug,
                    target_path=resolved,
                    source_kind="program_files",
                )

    return sorted(found.values(), key=lambda s: s.name.lower())


def get_applications_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override)
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "applications"
    return Path.home() / ".local" / "share" / "applications"


def render_desktop_entry(shortcut: WindowsShortcut) -> str:
    """Render an XDG .desktop entry that launches the Windows app via feather-run."""
    exec_parts = ["feather-run", "--bottle", shortcut.bottle_slug, str(shortcut.target_path)]
    if shortcut.arguments:
        exec_parts.append("--")
        exec_parts.extend(shlex.split(shortcut.arguments, posix=False))
    exec_line = " ".join(shlex.quote(part) for part in exec_parts)

    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        f"Name={shortcut.name}",
        f"Comment=Windows application in FeatherOS bottle '{shortcut.bottle_slug}'",
        f"Exec={exec_line}",
        "Icon=application-x-ms-dos-executable",
        "Terminal=false",
        "Categories=FeatherWindows;Application;",
        "StartupNotify=true",
        f"X-FeatherOS-Bottle={shortcut.bottle_slug}",
        f"X-FeatherOS-Target={shortcut.target_path}",
    ]
    return "\n".join(lines) + "\n"


def sync_bottle_shortcuts(
    manager: BottleManager,
    slug: str,
    *,
    applications_dir: str | Path | None = None,
) -> list[Path]:
    """Generate/update XDG .desktop launchers for a bottle and prune removed apps."""
    apps_dir = get_applications_dir(applications_dir)
    apps_dir.mkdir(parents=True, exist_ok=True)

    prefix_pattern = f"featheros-{slugify(slug)}-"
    shortcuts = discover_bottle_shortcuts(manager, slug)
    written: set[Path] = set()

    for sc in shortcuts:
        filename = f"{prefix_pattern}{slugify(sc.name)}.desktop"
        dest = apps_dir / filename
        dest.write_text(render_desktop_entry(sc), encoding="utf-8", newline="\n")
        written.add(dest)

    # Remove stale entries belonging to this bottle
    for existing in apps_dir.glob(f"{prefix_pattern}*.desktop"):
        if existing not in written:
            existing.unlink()

    return sorted(written)


def prune_bottle_shortcuts(
    slug: str, *, applications_dir: str | Path | None = None
) -> list[Path]:
    """Remove all FeatherOS-generated .desktop entries for a deleted bottle."""
    apps_dir = get_applications_dir(applications_dir)
    if not apps_dir.is_dir():
        return []
    removed: list[Path] = []
    for entry in apps_dir.glob(f"featheros-{slugify(slug)}-*.desktop"):
        entry.unlink()
        removed.append(entry)
    return removed


def sync_all_bottles(
    manager: BottleManager, *, applications_dir: str | Path | None = None
) -> dict[str, list[Path]]:
    """Sync Start Menu entries across every bottle managed by BottleManager."""
    results: dict[str, list[Path]] = {}
    for bottle in manager.list_bottles():
        results[bottle.slug] = sync_bottle_shortcuts(
            manager, bottle.slug, applications_dir=applications_dir
        )
    return results
