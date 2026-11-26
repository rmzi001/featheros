"""Pure-Python Windows PE/COFF and MSI binary inspector.

Inspects .exe, .dll, and .msi files without external dependencies so FeatherRun
can choose the right Wine architecture (win32/win64), subsystem (GUI vs console),
and installer handling automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import struct
from typing import Any

# OLE2 Compound Document magic (used by .msi Windows Installer packages)
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# PE COFF Machine constants
MACHINE_TYPES: dict[int, str] = {
    0x014C: "x86",
    0x8664: "x64",
    0xAA64: "arm64",
    0x01C0: "arm",
    0x01C4: "armnt",
}

# PE Optional Header Subsystem constants
SUBSYSTEM_TYPES: dict[int, str] = {
    1: "native",
    2: "gui",
    3: "console",
    7: "posix",
    9: "wince",
    10: "efi",
}

IMAGE_FILE_DLL = 0x2000

INSTALLER_MARKERS: list[tuple[bytes, str]] = [
    (b"NullsoftInst", "nsis"),
    (b"Inno Setup", "inno-setup"),
    (b"InstallShield", "installshield"),
    (b"WiX Toolset", "wix"),
    (b"Squirrel", "squirrel"),
    (b"7z\xbc\xaf\x27\x1c", "7zip-sfx"),
]

INSTALLER_NAME_HINTS = (
    "setup",
    "install",
    "installer",
    "redist",
    "vcredist",
    "updater",
)


@dataclass(frozen=True)
class BinaryInfo:
    """Structured metadata extracted from a Windows executable or installer."""

    path: str
    file_type: str  # "pe", "msi", "dos", "unknown"
    arch: str  # "x86", "x64", "arm64", "unknown"
    recommended_winearch: str  # "win32" or "win64"
    subsystem: str  # "gui", "console", "installer", "unknown"
    is_dll: bool
    is_installer: bool
    installer_kind: str | None
    valid: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _detect_installer_marker(data: bytes, filename: str) -> tuple[bool, str | None]:
    for marker, kind in INSTALLER_MARKERS:
        if marker in data:
            return True, kind

    stem = Path(filename).stem.lower()
    for hint in INSTALLER_NAME_HINTS:
        if hint in stem:
            return True, "heuristic"

    return False, None


def inspect_binary(path: str | Path) -> BinaryInfo:
    """Inspect a Windows .exe/.dll/.msi file and return structured metadata."""
    file_path = Path(path)
    if not file_path.exists():
        return BinaryInfo(
            path=str(file_path),
            file_type="unknown",
            arch="unknown",
            recommended_winearch="win64",
            subsystem="unknown",
            is_dll=False,
            is_installer=False,
            installer_kind=None,
            valid=False,
            error="File does not exist",
        )

    if not file_path.is_file():
        return BinaryInfo(
            path=str(file_path),
            file_type="unknown",
            arch="unknown",
            recommended_winearch="win64",
            subsystem="unknown",
            is_dll=False,
            is_installer=False,
            installer_kind=None,
            valid=False,
            error="Path is not a regular file",
        )

    # Read up to 2 MB for header + installer marker scan without blowing memory
    with file_path.open("rb") as fh:
        head = fh.read(2 * 1024 * 1024)

    suffix = file_path.suffix.lower()

    # Check MSI (OLE2 compound file)
    if head.startswith(OLE2_MAGIC) and suffix == ".msi":
        return BinaryInfo(
            path=str(file_path),
            file_type="msi",
            arch="x64",
            recommended_winearch="win64",
            subsystem="installer",
            is_dll=False,
            is_installer=True,
            installer_kind="msi",
            valid=True,
        )

    # Check MZ DOS header
    if len(head) < 64 or head[:2] != b"MZ":
        return BinaryInfo(
            path=str(file_path),
            file_type="unknown",
            arch="unknown",
            recommended_winearch="win64",
            subsystem="unknown",
            is_dll=False,
            is_installer=False,
            installer_kind=None,
            valid=False,
            error="Not a valid Windows PE or MSI binary (missing MZ/OLE2 magic)",
        )

    pe_offset = struct.unpack_from("<I", head, 0x3C)[0]
    if pe_offset + 24 > len(head) or head[pe_offset : pe_offset + 4] != b"PE\x00\x00":
        return BinaryInfo(
            path=str(file_path),
            file_type="dos",
            arch="x86",
            recommended_winearch="win32",
            subsystem="console",
            is_dll=False,
            is_installer=False,
            installer_kind=None,
            valid=True,
        )

    # COFF File Header (20 bytes right after "PE\0\0")
    coff_offset = pe_offset + 4
    machine, _num_sections, _ts, _sym_ptr, _num_sym, opt_hdr_size, characteristics = (
        struct.unpack_from("<HHIIIHH", head, coff_offset)
    )

    arch = MACHINE_TYPES.get(machine, "unknown")
    is_dll = bool(characteristics & IMAGE_FILE_DLL)

    # Optional Header follows COFF header
    opt_offset = coff_offset + 20
    subsystem = "unknown"
    if opt_hdr_size >= 70 and opt_offset + 70 <= len(head):
        opt_magic = struct.unpack_from("<H", head, opt_offset)[0]
        if opt_magic in (0x10B, 0x20B):  # PE32 or PE32+
            subsystem_code = struct.unpack_from("<H", head, opt_offset + 68)[0]
            subsystem = SUBSYSTEM_TYPES.get(subsystem_code, "unknown")
            if arch == "unknown":
                arch = "x64" if opt_magic == 0x20B else "x86"

    # WoW64 (win64 prefix) can run both x64 and most x86 binaries cleanly,
    # while pure 16-bit/legacy DOS or explicit win32 needs win32.
    # Recommend win64 for x64 and modern x86 (WoW64), unless explicitly pure DOS.
    recommended_winearch = "win64" if arch in ("x64", "x86") else "win64"

    is_installer, installer_kind = _detect_installer_marker(head, file_path.name)

    return BinaryInfo(
        path=str(file_path),
        file_type="pe",
        arch=arch,
        recommended_winearch=recommended_winearch,
        subsystem=subsystem,
        is_dll=is_dll,
        is_installer=is_installer,
        installer_kind=installer_kind,
        valid=True,
    )
