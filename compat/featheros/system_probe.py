"""Host hardware, graphics/Vulkan, and Wine stack readiness probe.

Allows FeatherRun to adapt cleanly between bare-metal GPUs (enabling DXVK/VKD3D)
and virtual machines like QEMU without GPU passthrough (falling back to WineD3D).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Any, Callable


CommandRunner = Callable[[list[str]], tuple[int, str]]
WhichLookup = Callable[[str], str | None]


@dataclass(frozen=True)
class SystemProbe:
    """Snapshot of the current system's Windows-compatibility capabilities."""

    platform_system: str
    machine: str
    cpu_count: int
    ram_total_mb: int | None
    ram_available_mb: int | None
    wine_path: str | None
    wine64_path: str | None
    wineserver_path: str | None
    winetricks_path: str | None
    steam_path: str | None
    gamemoderun_path: str | None
    mangohud_path: str | None
    multiarch_i386: bool
    vulkan_hardware_ready: bool
    vulkan_device_name: str | None
    vulkan_software_only: bool
    dxvk_available: bool
    vkd3d_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def can_run_wine(self) -> bool:
        return bool(self.wine_path or self.wine64_path)

    @property
    def recommended_graphics_backend(self) -> str:
        if self.vulkan_hardware_ready and self.dxvk_available:
            return "dxvk"
        return "wined3d"


def _default_run_command(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError):
        return 127, ""


def _read_linux_meminfo(meminfo_path: Path = Path("/proc/meminfo")) -> tuple[int | None, int | None]:
    if not meminfo_path.exists():
        return None, None
    total_kb = None
    avail_kb = None
    try:
        for line in meminfo_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                avail_kb = int(line.split()[1])
    except (OSError, ValueError):
        return None, None
    return (
        total_kb // 1024 if total_kb is not None else None,
        avail_kb // 1024 if avail_kb is not None else None,
    )


def _probe_vulkan(
    which: WhichLookup,
    run_cmd: CommandRunner,
    icd_dirs: tuple[Path, ...] = (
        Path("/usr/share/vulkan/icd.d"),
        Path("/etc/vulkan/icd.d"),
    ),
) -> tuple[bool, str | None, bool]:
    """Return (hardware_ready, device_name, software_only)."""
    vulkaninfo = which("vulkaninfo")
    if vulkaninfo:
        rc, out = run_cmd([vulkaninfo, "--summary"])
        if rc == 0 and out:
            device_name = None
            hw_found = False
            sw_found = False
            for line in out.splitlines():
                stripped = line.strip()
                if stripped.startswith("deviceName"):
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        candidate = parts[1].strip()
                        if device_name is None:
                            device_name = candidate
                        low = candidate.lower()
                        if "llvmpipe" in low or "lavapipe" in low or "swiftshader" in low:
                            sw_found = True
                        else:
                            hw_found = True
                elif stripped.startswith("deviceType"):
                    low = stripped.lower()
                    if "discrete_gpu" in low or "integrated_gpu" in low or "virtual_gpu" in low:
                        hw_found = True
                    elif "cpu" in low:
                        sw_found = True
            if hw_found:
                return True, device_name, False
            if sw_found:
                return False, device_name, True

    # Fallback: check Vulkan ICD files when vulkaninfo is unavailable
    hw_icds: list[str] = []
    sw_icds: list[str] = []
    for directory in icd_dirs:
        if not directory.is_dir():
            continue
        for entry in directory.glob("*.json"):
            name = entry.name.lower()
            if "lvp" in name or "lavapipe" in name or "swiftshader" in name:
                sw_icds.append(entry.name)
            else:
                hw_icds.append(entry.name)

    if hw_icds:
        return True, f"icd:{hw_icds[0]}", False
    if sw_icds:
        return False, f"icd:{sw_icds[0]}", True
    return False, None, False


def _probe_multiarch_i386(which: WhichLookup, run_cmd: CommandRunner) -> bool:
    dpkg = which("dpkg")
    if not dpkg:
        return False
    rc, out = run_cmd([dpkg, "--print-foreign-architectures"])
    if rc != 0:
        return False
    return "i386" in {line.strip() for line in out.splitlines()}


def _has_any_path(paths: tuple[Path, ...]) -> bool:
    return any(p.exists() for p in paths)


def probe_system(
    which: WhichLookup = shutil.which,
    run_cmd: CommandRunner = _default_run_command,
    meminfo_path: Path = Path("/proc/meminfo"),
    icd_dirs: tuple[Path, ...] = (
        Path("/usr/share/vulkan/icd.d"),
        Path("/etc/vulkan/icd.d"),
    ),
    dxvk_paths: tuple[Path, ...] = (
        Path("/usr/lib/dxvk"),
        Path("/usr/share/dxvk"),
        Path("/usr/lib/x86_64-linux-gnu/wine/x86_64-windows/dxvk_d3d11.dll"),
        Path("/usr/share/featheros/dxvk"),
    ),
    vkd3d_paths: tuple[Path, ...] = (
        Path("/usr/lib/vkd3d-proton"),
        Path("/usr/share/vkd3d-proton"),
        Path("/usr/share/featheros/vkd3d-proton"),
    ),
) -> SystemProbe:
    """Collect a complete compatibility readiness snapshot for the current host."""
    ram_total, ram_avail = _read_linux_meminfo(meminfo_path)
    vk_hw, vk_dev, vk_sw = _probe_vulkan(which=which, run_cmd=run_cmd, icd_dirs=icd_dirs)

    dxvk_available = _has_any_path(dxvk_paths) or bool(which("dxvk-setup"))
    vkd3d_available = _has_any_path(vkd3d_paths)

    return SystemProbe(
        platform_system=platform.system(),
        machine=platform.machine(),
        cpu_count=os.cpu_count() or 1,
        ram_total_mb=ram_total,
        ram_available_mb=ram_avail,
        wine_path=which("wine"),
        wine64_path=which("wine64"),
        wineserver_path=which("wineserver"),
        winetricks_path=which("winetricks"),
        steam_path=which("steam"),
        gamemoderun_path=which("gamemoderun"),
        mangohud_path=which("mangohud"),
        multiarch_i386=_probe_multiarch_i386(which=which, run_cmd=run_cmd),
        vulkan_hardware_ready=vk_hw,
        vulkan_device_name=vk_dev,
        vulkan_software_only=vk_sw,
        dxvk_available=dxvk_available,
        vkd3d_available=vkd3d_available,
    )
