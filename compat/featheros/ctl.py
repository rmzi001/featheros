"""feather-ctl: FeatherOS system diagnostics and performance profile manager.

Supports switching between Balanced, Low-RAM (2-4 GB PCs), and Gaming profiles
so users can trade visual polish for raw memory or frame latency on demand.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Sequence

from . import __version__
from .bottles import BottleManager
from .runners import list_installed_runners
from .system_probe import SystemProbe, probe_system


@dataclass(frozen=True)
class PerformanceProfile:
    """Definition of a FeatherOS desktop/system tuning profile."""

    name: str
    label: str
    description: str
    compositor_enabled: bool
    swappiness: int
    cpu_governor: str
    default_gamemode: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


PROFILES: dict[str, PerformanceProfile] = {
    "balanced": PerformanceProfile(
        name="balanced",
        label="Balanced",
        description="Lightweight compositor on, smooth desktop visuals, ~300 MB RAM idle.",
        compositor_enabled=True,
        swappiness=60,
        cpu_governor="schedutil",
        default_gamemode=False,
    ),
    "low-ram": PerformanceProfile(
        name="low-ram",
        label="Low-RAM Saver",
        description="Disables Picom compositor and prioritizes zram compression for 2-4 GB PCs.",
        compositor_enabled=False,
        swappiness=100,
        cpu_governor="powersave",
        default_gamemode=False,
    ),
    "gaming": PerformanceProfile(
        name="gaming",
        label="Gaming Performance",
        description="Disables compositor for zero-latency fullscreen and requests performance CPU scaling.",
        compositor_enabled=False,
        swappiness=30,
        cpu_governor="performance",
        default_gamemode=True,
    ),
}


def get_config_dir(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override)
    xdg_cfg = os.environ.get("XDG_CONFIG_HOME")
    if xdg_cfg:
        return Path(xdg_cfg) / "featheros"
    return Path.home() / ".config" / "featheros"


def get_active_profile(config_dir: str | Path | None = None) -> PerformanceProfile:
    cfg_file = get_config_dir(config_dir) / "profile.json"
    if cfg_file.is_file():
        try:
            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            name = str(data.get("profile", "balanced"))
            if name in PROFILES:
                return PROFILES[name]
        except (OSError, ValueError):
            pass
    return PROFILES["balanced"]


def build_profile_actions(profile: PerformanceProfile) -> list[list[str]]:
    """Compute non-privileged desktop actions for XFCE 4.20 (with Openbox/picom fallback)."""
    actions: list[list[str]] = []
    if profile.compositor_enabled:
        actions.append(
            ["xfconf-query", "-c", "xfwm4", "-p", "/general/use_compositing", "-s", "true"]
        )
        actions.append(["picom", "--config", "/etc/xdg/featheros/picom.conf", "-b"])
    else:
        actions.append(
            ["xfconf-query", "-c", "xfwm4", "-p", "/general/use_compositing", "-s", "false"]
        )
        actions.append(["pkill", "-x", "picom"])
    return actions


def apply_profile(
    profile_name: str,
    *,
    config_dir: str | Path | None = None,
    dry_run: bool = False,
    runner: Callable[[list[str]], int] | None = None,
) -> dict[str, Any]:
    """Persist and apply a FeatherOS performance profile."""
    key = profile_name.strip().lower()
    if key not in PROFILES:
        raise ValueError(f"Unknown profile '{profile_name}'. Valid: {tuple(PROFILES.keys())}")

    profile = PROFILES[key]
    actions = build_profile_actions(profile)
    cfg_root = get_config_dir(config_dir)
    cfg_file = cfg_root / "profile.json"

    executed: list[dict[str, Any]] = []
    if not dry_run:
        cfg_root.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text(
            json.dumps({"profile": profile.name, "settings": profile.to_dict()}, indent=2) + "\n",
            encoding="utf-8",
        )
        for cmd in actions:
            if runner is not None:
                rc = runner(cmd)
            else:
                try:
                    rc = subprocess.run(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                except OSError:
                    rc = 127
            executed.append({"command": cmd, "returncode": rc})

    return {
        "profile": profile.to_dict(),
        "config_file": str(cfg_file),
        "dry_run": dry_run,
        "actions": actions,
        "executed": executed,
    }


def collect_system_status(
    *,
    home: str | Path | None = None,
    config_dir: str | Path | None = None,
    probe: SystemProbe | None = None,
) -> dict[str, Any]:
    """Return a unified status payload for feather-ctl and feather-compat."""
    sys_probe = probe or probe_system()
    mgr = BottleManager(home=home)
    profile = get_active_profile(config_dir=config_dir)
    runners = list_installed_runners(home=home)
    return {
        "os": "FeatherOS",
        "version": __version__,
        "active_profile": profile.to_dict(),
        "bottles_count": len(mgr.list_bottles()),
        "runners": [r.to_dict() for r in runners],
        "system": sys_probe.to_dict(),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feather-ctl",
        description="FeatherOS system status, performance profiles, and runner control",
    )
    parser.add_argument("--home", help="Override FEATHEROS_HOME data directory")
    parser.add_argument("--config-dir", help="Override FeatherOS config directory")
    parser.add_argument("--version", action="version", version=f"feather-ctl {__version__}")

    sub = parser.add_subparsers(dest="command")

    p_status = sub.add_parser("status", help="Show FeatherOS hardware, profile, and Wine status")
    p_status.add_argument("--json", action="store_true")

    p_prof = sub.add_parser("profile", help="Get or set active performance profile")
    p_prof.add_argument("name", nargs="?", choices=tuple(PROFILES.keys()))
    p_prof.add_argument("--dry-run", action="store_true")
    p_prof.add_argument("--json", action="store_true")

    p_run = sub.add_parser("runners", help="List installed Wine/GE-Proton runners")
    p_run.add_argument("--json", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if not args.command or args.command == "status":
        status = collect_system_status(home=args.home, config_dir=args.config_dir)
        if getattr(args, "json", False):
            print(json.dumps(status, indent=2))
        else:
            prof = status["active_profile"]
            sys_info = status["system"]
            print(f"FeatherOS v{status['version']} — System Control")
            print(f"  Profile:      {prof['label']} ({prof['name']})")
            print(f"  Bottles:      {status['bottles_count']}")
            print(f"  Runners:      {', '.join(r['name'] for r in status['runners'])}")
            print(f"  Platform:     {sys_info['platform_system']} ({sys_info['machine']})")
            if sys_info["ram_total_mb"] is not None:
                print(
                    f"  Memory:       {sys_info['ram_available_mb']} MB free / "
                    f"{sys_info['ram_total_mb']} MB total"
                )
            print(f"  Vulkan HW:    {sys_info['vulkan_hardware_ready']}")
        return 0

    if args.command == "profile":
        if not args.name:
            prof = get_active_profile(config_dir=args.config_dir)
            if args.json:
                print(json.dumps(prof.to_dict(), indent=2))
            else:
                print(f"Active profile: {prof.label} ({prof.name}) — {prof.description}")
            return 0

        res = apply_profile(args.name, config_dir=args.config_dir, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            mode = " (dry-run)" if args.dry_run else ""
            print(f"Switched profile to {res['profile']['label']}{mode}.")
        return 0

    if args.command == "runners":
        runners = list_installed_runners(home=args.home)
        if args.json:
            print(json.dumps([r.to_dict() for r in runners], indent=2))
        else:
            for r in runners:
                print(f"- {r.name} [{r.kind}] -> {r.wine_binary}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
