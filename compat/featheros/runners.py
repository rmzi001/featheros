"""Wine / GE-Proton runner discovery, safe extraction, installer, and runtime presets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tarfile
import tempfile
from typing import Any, Callable
import urllib.request

from . import __version__
from .bottles import get_featheros_home

GE_PROTON_RELEASES_API = (
    "https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest"
)


@dataclass(frozen=True)
class RuntimePreset:
    """Common Windows redistributable/runtime installed via winetricks."""

    id: str
    label: str
    description: str
    verbs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RUNTIME_PRESETS: tuple[RuntimePreset, ...] = (
    RuntimePreset(
        id="vcrun2022",
        label="Visual C++ 2015–2022",
        description="Required by most modern Windows desktop apps and PC games.",
        verbs=("vcrun2022",),
    ),
    RuntimePreset(
        id="corefonts",
        label="Windows Core Fonts",
        description="Arial, Times New Roman, Verdana, Tahoma for crisp UI text.",
        verbs=("corefonts", "tahoma"),
    ),
    RuntimePreset(
        id="dotnet48",
        label=".NET Framework 4.8",
        description="Required by many Windows productivity tools and launchers.",
        verbs=("dotnet48",),
    ),
    RuntimePreset(
        id="d3dx9",
        label="Legacy DirectX 9 Runtimes",
        description="Helps older 2000s games and Win32 graphics utilities run smoothly.",
        verbs=("d3dx9", "d3dcompiler_47"),
    ),
    RuntimePreset(
        id="dxvk",
        label="DXVK (DirectX 9/10/11 -> Vulkan)",
        description="High-performance Vulkan translation for modern GPUs.",
        verbs=("dxvk",),
    ),
)


@dataclass(frozen=True)
class InstalledRunner:
    """A Wine or Proton-GE runner available on the local system."""

    name: str
    kind: str  # "system" or "ge-proton" or "custom"
    wine_binary: str | None
    root_dir: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReleaseAsset:
    """Metadata for a downloadable GE-Proton release tarball."""

    tag: str
    asset_name: str
    download_url: str
    size_bytes: int


def list_installed_runners(home: str | Path | None = None) -> list[InstalledRunner]:
    """Return system-wine plus any custom runners installed under FEATHEROS_HOME/runners."""
    runners: list[InstalledRunner] = [
        InstalledRunner(
            name="system-wine",
            kind="system",
            wine_binary="wine",
            root_dir=None,
        )
    ]
    runners_dir = get_featheros_home(home) / "runners"
    if not runners_dir.is_dir():
        return runners

    for entry in sorted(runners_dir.iterdir()):
        if not entry.is_dir():
            continue
        proton_wine = entry / "files" / "bin" / "wine"
        generic_wine = entry / "bin" / "wine"
        if proton_wine.is_file():
            runners.append(
                InstalledRunner(
                    name=entry.name,
                    kind="ge-proton" if "proton" in entry.name.lower() else "custom",
                    wine_binary=str(proton_wine),
                    root_dir=str(entry),
                )
            )
        elif generic_wine.is_file():
            runners.append(
                InstalledRunner(
                    name=entry.name,
                    kind="custom",
                    wine_binary=str(generic_wine),
                    root_dir=str(entry),
                )
            )
    return runners


def parse_ge_proton_release(release_json: dict[str, Any]) -> ReleaseAsset:
    """Extract the .tar.gz download asset from a GitHub Release API payload."""
    tag = str(release_json.get("tag_name") or "").strip()
    if not tag:
        raise ValueError("Release payload missing tag_name")

    for asset in release_json.get("assets", []):
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.endswith(".tar.gz") and url:
            return ReleaseAsset(
                tag=tag,
                asset_name=name,
                download_url=url,
                size_bytes=int(asset.get("size") or 0),
            )
    raise ValueError(f"No .tar.gz asset found in release '{tag}'")


def fetch_latest_ge_proton(
    fetcher: Callable[[str], bytes] | None = None,
) -> ReleaseAsset:
    """Query GitHub for the latest GE-Proton release tarball metadata."""
    if fetcher is None:
        req = urllib.request.Request(
            GE_PROTON_RELEASES_API,
            headers={"User-Agent": f"FeatherOS-RunnerManager/{__version__}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
    else:
        raw = fetcher(GE_PROTON_RELEASES_API)

    payload = json.loads(raw.decode("utf-8"))
    return parse_ge_proton_release(payload)


def _ensure_within(dest: Path, candidate: Path, label: str) -> None:
    try:
        candidate.relative_to(dest)
    except ValueError as exc:
        raise ValueError(f"Unsafe path in archive: {label}") from exc


def safe_extract_tarball(archive_path: str | Path, dest_dir: str | Path) -> Path:
    """Safely extract a runner .tar.gz archive, blocking path & symlink traversal."""
    archive = Path(archive_path)
    dest = Path(dest_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive, "r:*") as tf:
        for member in tf.getmembers():
            member_path = (dest / member.name).resolve()
            _ensure_within(dest, member_path, member.name)
            if member.issym() or member.islnk():
                link_target = (member_path.parent / member.linkname).resolve()
                _ensure_within(dest, link_target, f"{member.name} -> {member.linkname}")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(dest, filter="data")
        else:
            tf.extractall(dest)

    return dest


def install_ge_proton(
    *,
    home: str | Path | None = None,
    fetcher: Callable[[str], bytes] | None = None,
    downloader: Callable[[str, Path], None] | None = None,
) -> ReleaseAsset:
    """Download and safely extract the latest GE-Proton runner into FEATHEROS_HOME/runners."""
    asset = fetch_latest_ge_proton(fetcher=fetcher)
    runners_dir = get_featheros_home(home) / "runners"
    runners_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / asset.asset_name
        if downloader is not None:
            downloader(asset.download_url, archive_path)
        else:
            req = urllib.request.Request(
                asset.download_url,
                headers={"User-Agent": f"FeatherOS-RunnerManager/{__version__}"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp, archive_path.open("wb") as out:
                while chunk := resp.read(1024 * 1024):
                    out.write(chunk)
        safe_extract_tarball(archive_path, runners_dir)

    return asset
