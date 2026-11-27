"""Isolated Wine/Proton Bottle manager and launch plan builder.

Each Windows application can run in its own isolated bottle (separate WINEPREFIX,
Windows version, DXVK/VKD3D toggles, DPI, virtual desktop) or share the fast
default bottle to conserve disk space.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .pe_inspector import BinaryInfo, inspect_binary
from .system_probe import SystemProbe, probe_system

VALID_WINDOWS_VERSIONS = ("win11", "win10", "win81", "win7", "winxp")
VALID_ARCHES = ("win64", "win32")

DXVK_DLLS = ("d3d9", "d3d10core", "d3d11", "dxgi")
VKD3D_DLLS = ("d3d12", "d3d12core")


def slugify(name: str) -> str:
    """Convert an arbitrary bottle or app name into a safe filesystem slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip().lower()).strip("-._")
    return cleaned or "default"


def get_featheros_home(override: str | Path | None = None) -> Path:
    """Resolve the FeatherOS data directory (defaults to ~/.local/share/featheros)."""
    if override is not None:
        return Path(override)
    env_home = os.environ.get("FEATHEROS_HOME")
    if env_home:
        return Path(env_home)
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data:
        return Path(xdg_data) / "featheros"
    return Path.home() / ".local" / "share" / "featheros"


@dataclass
class BottleConfig:
    """Persisted configuration for a single FeatherOS Windows compatibility bottle."""

    name: str
    slug: str
    arch: str = "win64"
    windows_version: str = "win10"
    dxvk: bool = True
    vkd3d: bool = True
    esync: bool = True
    fsync: bool = True
    virtual_desktop: str | None = None  # e.g., "1280x720"
    dpi: int = 96
    runner: str = "system-wine"  # "system-wine" or path/name of custom Proton/Wine runner
    gamemode: bool = False
    mangohud: bool = False
    dll_overrides: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    last_used: str | None = None

    def validate(self) -> None:
        if self.arch not in VALID_ARCHES:
            raise ValueError(f"Unsupported bottle arch '{self.arch}'. Valid: {VALID_ARCHES}")
        if self.windows_version not in VALID_WINDOWS_VERSIONS:
            raise ValueError(
                f"Unsupported windows_version '{self.windows_version}'. "
                f"Valid: {VALID_WINDOWS_VERSIONS}"
            )
        if self.virtual_desktop:
            if not re.fullmatch(r"\d{3,5}x\d{3,5}", self.virtual_desktop):
                raise ValueError(
                    f"Invalid virtual_desktop '{self.virtual_desktop}'. Expected WIDTHxHEIGHT."
                )
        if not (72 <= int(self.dpi) <= 480):
            raise ValueError(f"Invalid DPI {self.dpi}. Must be between 72 and 480.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BottleConfig":
        cfg = cls(
            name=str(data["name"]),
            slug=str(data["slug"]),
            arch=str(data.get("arch", "win64")),
            windows_version=str(data.get("windows_version", "win10")),
            dxvk=bool(data.get("dxvk", True)),
            vkd3d=bool(data.get("vkd3d", True)),
            esync=bool(data.get("esync", True)),
            fsync=bool(data.get("fsync", True)),
            virtual_desktop=data.get("virtual_desktop"),
            dpi=int(data.get("dpi", 96)),
            runner=str(data.get("runner", "system-wine")),
            gamemode=bool(data.get("gamemode", False)),
            mangohud=bool(data.get("mangohud", False)),
            dll_overrides=dict(data.get("dll_overrides", {})),
            env=dict(data.get("env", {})),
            created_at=str(
                data.get(
                    "created_at",
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
            ),
            last_used=data.get("last_used"),
        )
        cfg.validate()
        return cfg


@dataclass(frozen=True)
class LaunchPlan:
    """Resolved execution plan for running a Windows executable or installer."""

    bottle: BottleConfig
    prefix_path: Path
    binary_info: BinaryInfo
    command: list[str]
    env: dict[str, str]
    effective_backend: str  # "dxvk", "dxvk+vkd3d", "wined3d"
    notices: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "bottle": self.bottle.to_dict(),
            "prefix_path": str(self.prefix_path),
            "binary_info": self.binary_info.to_dict(),
            "command": self.command,
            "env": self.env,
            "effective_backend": self.effective_backend,
            "notices": self.notices,
        }


def _format_dll_overrides(overrides: dict[str, str]) -> str:
    return ";".join(f"{dll}={mode}" for dll, mode in sorted(overrides.items()))


class BottleManager:
    """Creates, inspects, configures, and deletes isolated FeatherOS bottles."""

    def __init__(self, home: str | Path | None = None) -> None:
        self.home = get_featheros_home(home)
        self.bottles_dir = self.home / "bottles"
        self.runners_dir = self.home / "runners"
        self.bottles_dir.mkdir(parents=True, exist_ok=True)
        self.runners_dir.mkdir(parents=True, exist_ok=True)

    def bottle_dir(self, slug: str) -> Path:
        return self.bottles_dir / slugify(slug)

    def prefix_dir(self, slug: str) -> Path:
        return self.bottle_dir(slug) / "prefix"

    def config_path(self, slug: str) -> Path:
        return self.bottle_dir(slug) / "bottle.json"

    def exists(self, slug: str) -> bool:
        return self.config_path(slug).is_file()

    def list_bottles(self) -> list[BottleConfig]:
        bottles: list[BottleConfig] = []
        if not self.bottles_dir.exists():
            return bottles
        for entry in sorted(self.bottles_dir.iterdir()):
            cfg_file = entry / "bottle.json"
            if cfg_file.is_file():
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                bottles.append(BottleConfig.from_dict(data))
        return bottles

    def get_bottle(self, name_or_slug: str) -> BottleConfig:
        slug = slugify(name_or_slug)
        cfg_file = self.config_path(slug)
        if not cfg_file.is_file():
            raise KeyError(f"Bottle '{slug}' does not exist")
        return BottleConfig.from_dict(json.loads(cfg_file.read_text(encoding="utf-8")))

    def create_bottle(
        self,
        name: str,
        *,
        arch: str = "win64",
        windows_version: str = "win10",
        dxvk: bool = True,
        vkd3d: bool = True,
        esync: bool = True,
        fsync: bool = True,
        virtual_desktop: str | None = None,
        dpi: int = 96,
        runner: str = "system-wine",
        gamemode: bool = False,
        mangohud: bool = False,
        overwrite: bool = False,
    ) -> BottleConfig:
        slug = slugify(name)
        if self.exists(slug) and not overwrite:
            raise FileExistsError(f"Bottle '{slug}' already exists")

        cfg = BottleConfig(
            name=name.strip() or slug,
            slug=slug,
            arch=arch,
            windows_version=windows_version,
            dxvk=dxvk,
            vkd3d=vkd3d,
            esync=esync,
            fsync=fsync,
            virtual_desktop=virtual_desktop,
            dpi=dpi,
            runner=runner,
            gamemode=gamemode,
            mangohud=mangohud,
        )
        cfg.validate()

        bdir = self.bottle_dir(slug)
        pdir = self.prefix_dir(slug)
        (pdir / "drive_c" / "Program Files").mkdir(parents=True, exist_ok=True)
        (pdir / "drive_c" / "Program Files (x86)").mkdir(parents=True, exist_ok=True)
        (
            pdir
            / "drive_c"
            / "ProgramData"
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        ).mkdir(parents=True, exist_ok=True)
        current_user = getpass.getuser() or "feather"
        (pdir / "drive_c" / "users" / current_user / "Desktop").mkdir(parents=True, exist_ok=True)

        self.save_bottle(cfg)
        return cfg

    def ensure_bottle(
        self,
        name: str = "default",
        *,
        arch: str = "win64",
        windows_version: str = "win10",
    ) -> BottleConfig:
        slug = slugify(name)
        if self.exists(slug):
            return self.get_bottle(slug)
        return self.create_bottle(name, arch=arch, windows_version=windows_version)

    def save_bottle(self, cfg: BottleConfig) -> None:
        cfg.validate()
        cfg_file = self.config_path(cfg.slug)
        cfg_file.parent.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(json.dumps(cfg.to_dict(), indent=2) + "\n", encoding="utf-8")

    def update_bottle(self, slug: str, **updates: Any) -> BottleConfig:
        cfg = self.get_bottle(slug)
        data = cfg.to_dict()
        for key, value in updates.items():
            if key not in data:
                raise KeyError(f"Unknown bottle config field: '{key}'")
            data[key] = value
        updated = BottleConfig.from_dict(data)
        self.save_bottle(updated)
        return updated

    def touch_last_used(self, slug: str) -> BottleConfig:
        return self.update_bottle(
            slug, last_used=datetime.now(timezone.utc).isoformat(timespec="seconds")
        )

    def delete_bottle(self, slug: str) -> bool:
        bdir = self.bottle_dir(slug)
        if not bdir.exists():
            return False
        shutil.rmtree(bdir)
        return True

    def resolve_runner_binary(self, cfg: BottleConfig, probe: SystemProbe) -> tuple[str, list[str]]:
        """Resolve the Wine/Proton executable path for a bottle."""
        notices: list[str] = []
        if cfg.runner and cfg.runner != "system-wine":
            custom = Path(cfg.runner)
            if not custom.is_absolute():
                # Check installed FeatherOS runners directory (e.g., GE-Proton)
                candidate_wine = self.runners_dir / cfg.runner / "files" / "bin" / "wine"
                candidate_bin = self.runners_dir / cfg.runner / "bin" / "wine"
                if candidate_wine.exists():
                    return str(candidate_wine), notices
                if candidate_bin.exists():
                    return str(candidate_bin), notices
            elif custom.exists():
                return str(custom), notices
            notices.append(
                f"Configured runner '{cfg.runner}' not found; falling back to system Wine."
            )

        if cfg.arch == "win64" and probe.wine64_path and not probe.wine_path:
            return probe.wine64_path, notices
        return probe.wine_path or probe.wine64_path or "wine", notices

    def build_launch_plan(
        self,
        target: str | Path,
        bottle_name: str | None = None,
        *,
        isolated: bool = False,
        extra_args: list[str] | None = None,
        debug: bool = False,
        probe: SystemProbe | None = None,
    ) -> LaunchPlan:
        """Inspect a Windows binary and compute the exact Wine/Proton command and env."""
        target_path = Path(target).resolve()
        info = inspect_binary(target_path)
        sys_probe = probe or probe_system()

        if bottle_name:
            chosen_name = bottle_name
        elif isolated:
            chosen_name = slugify(target_path.stem)
        else:
            chosen_name = "default"

        if not info.valid:
            # Never create orphan bottle directories on disk for invalid/ARM64 binaries
            slug = slugify(chosen_name)
            ephemeral = BottleConfig(name=chosen_name, slug=slug, arch=info.recommended_winearch)
            return LaunchPlan(
                bottle=ephemeral,
                prefix_path=self.prefix_dir(slug),
                binary_info=info,
                command=[],
                env={},
                effective_backend="wined3d",
                notices=[],
            )

        cfg = self.ensure_bottle(chosen_name, arch=info.recommended_winearch)
        prefix_path = self.prefix_dir(cfg.slug)

        notices: list[str] = []
        wine_bin, runner_notices = self.resolve_runner_binary(cfg, sys_probe)
        notices.extend(runner_notices)

        overrides: dict[str, str] = {}
        # Disable Wine's intrusive automatic Gecko/Mono prompts during silent first launch
        overrides["winemenubuilder.exe"] = "d"

        use_dxvk = False
        use_vkd3d = False
        if cfg.dxvk:
            if sys_probe.vulkan_hardware_ready and sys_probe.dxvk_available:
                use_dxvk = True
                for dll in DXVK_DLLS:
                    overrides[dll] = "n,b"
            else:
                for dll in DXVK_DLLS:
                    overrides[dll] = "b"
                if not sys_probe.vulkan_hardware_ready:
                    notices.append(
                        "Vulkan hardware acceleration unavailable; falling back to WineD3D (VM-safe mode)."
                    )
                else:
                    notices.append("DXVK libraries not installed; using built-in WineD3D.")
        else:
            for dll in DXVK_DLLS:
                overrides[dll] = "b"

        if cfg.vkd3d:
            if sys_probe.vulkan_hardware_ready and sys_probe.vkd3d_available:
                use_vkd3d = True
                for dll in VKD3D_DLLS:
                    overrides[dll] = "n,b"
            else:
                for dll in VKD3D_DLLS:
                    overrides[dll] = "b"

        # User-defined DLL overrides take precedence
        overrides.update(cfg.dll_overrides)

        if use_dxvk and use_vkd3d:
            effective_backend = "dxvk+vkd3d"
        elif use_dxvk:
            effective_backend = "dxvk"
        else:
            effective_backend = "wined3d"

        env: dict[str, str] = {
            "WINEPREFIX": str(prefix_path),
            "WINEARCH": cfg.arch,
            "WINEDLLOVERRIDES": _format_dll_overrides(overrides),
            "WINEESYNC": "1" if cfg.esync else "0",
            "WINEFSYNC": "1" if cfg.fsync else "0",
            "FEATHEROS_BOTTLE": cfg.slug,
            "FEATHEROS_BACKEND": effective_backend,
        }
        if not debug:
            env["WINEDEBUG"] = "-all"
        if not use_dxvk:
            env["PROTON_USE_WINED3D"] = "1"
        if cfg.dpi != 96:
            env["FEATHEROS_DPI"] = str(cfg.dpi)

        env.update(cfg.env)

        # Honor global Gaming Performance profile default_gamemode automatically
        profile_gamemode = False
        try:
            xdg_cfg = os.environ.get("XDG_CONFIG_HOME")
            prof_file = (
                (Path(xdg_cfg) / "featheros" / "profile.json")
                if xdg_cfg
                else (Path.home() / ".config" / "featheros" / "profile.json")
            )
            if prof_file.is_file():
                profile_gamemode = json.loads(prof_file.read_text(encoding="utf-8")).get("profile") == "gaming"
        except (OSError, ValueError):
            profile_gamemode = False

        cmd: list[str] = []
        if cfg.gamemode or profile_gamemode:
            if sys_probe.gamemoderun_path:
                cmd.append(sys_probe.gamemoderun_path)
            elif cfg.gamemode:
                notices.append("GameMode enabled on bottle, but 'gamemoderun' is not installed.")
        if cfg.mangohud:
            if sys_probe.mangohud_path:
                cmd.append(sys_probe.mangohud_path)
            else:
                notices.append("MangoHud enabled on bottle, but 'mangohud' is not installed.")

        cmd.append(wine_bin)

        if cfg.virtual_desktop:
            cmd.extend(["explorer", f"/desktop={cfg.slug},{cfg.virtual_desktop}"])

        if info.file_type == "msi":
            cmd.extend(["msiexec", "/i", str(target_path)])
        else:
            cmd.append(str(target_path))

        if extra_args:
            cmd.extend(extra_args)

        return LaunchPlan(
            bottle=cfg,
            prefix_path=prefix_path,
            binary_info=info,
            command=cmd,
            env=env,
            effective_backend=effective_backend,
            notices=notices,
        )

    def build_winetricks_command(
        self, slug: str, verbs: list[str], *, unattended: bool = True
    ) -> tuple[list[str], dict[str, str]]:
        """Build a winetricks command and env for installing Windows runtimes."""
        cfg = self.get_bottle(slug)
        if not verbs:
            raise ValueError("At least one winetricks verb is required")
        cmd = ["winetricks"]
        if unattended:
            cmd.append("-q")
        cmd.extend(verbs)
        env = {
            "WINEPREFIX": str(self.prefix_dir(cfg.slug)),
            "WINEARCH": cfg.arch,
        }
        return cmd, env

    def build_apply_settings_commands(
        self, slug: str, probe: SystemProbe | None = None
    ) -> tuple[list[list[str]], dict[str, str]]:
        """Build Wine commands that apply persisted windows_version, DPI, and DXVK into the prefix."""
        cfg = self.get_bottle(slug)
        sys_probe = probe or probe_system()
        wine_bin, _ = self.resolve_runner_binary(cfg, sys_probe)
        prefix = self.prefix_dir(cfg.slug)

        commands: list[list[str]] = [
            [wine_bin, "winecfg", "-v", cfg.windows_version],
            [
                wine_bin,
                "reg",
                "add",
                r"HKCU\Control Panel\Desktop",
                "/v",
                "LogPixels",
                "/t",
                "REG_DWORD",
                "/d",
                str(cfg.dpi),
                "/f",
            ],
        ]
        if cfg.dxvk and sys_probe.vulkan_hardware_ready and sys_probe.dxvk_available:
            dxvk_setup = shutil.which("dxvk-setup")
            if dxvk_setup:
                commands.append([dxvk_setup, "install"])

        env = {
            "WINEPREFIX": str(prefix),
            "WINEARCH": cfg.arch,
            "WINEDEBUG": "-all",
        }
        return commands, env

    def apply_bottle_settings(
        self, slug: str, probe: SystemProbe | None = None
    ) -> list[tuple[list[str], int]]:
        """Apply windows_version, DPI, and DXVK setup into the bottle's Wine prefix."""
        sys_probe = probe or probe_system()
        if not sys_probe.can_run_wine:
            return []
        commands, env = self.build_apply_settings_commands(slug, probe=sys_probe)
        merged = os.environ.copy()
        merged.update(env)
        results: list[tuple[list[str], int]] = []
        for cmd in commands:
            try:
                rc = subprocess.run(
                    cmd,
                    env=merged,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                    check=False,
                ).returncode
            except (OSError, subprocess.SubprocessError):
                rc = 127
            results.append((cmd, rc))
        return results
