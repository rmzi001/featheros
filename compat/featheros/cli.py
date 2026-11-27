"""feather-run CLI and XDG MIME handler for Windows .exe and .msi software."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from . import __version__
from .bottles import BottleManager, VALID_ARCHES, VALID_WINDOWS_VERSIONS
from .pe_inspector import inspect_binary
from .shortcuts import prune_bottle_shortcuts, sync_all_bottles, sync_bottle_shortcuts
from .system_probe import probe_system


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _cmd_inspect(args: argparse.Namespace) -> int:
    info = inspect_binary(args.target)
    if args.json:
        _print_json(info.to_dict())
    else:
        print(f"File:        {info.path}")
        print(f"Valid:       {info.valid}")
        print(f"Type:        {info.file_type}")
        print(f"Arch:        {info.arch} (recommended WINEARCH={info.recommended_winearch})")
        print(f"Subsystem:   {info.subsystem}")
        print(f"Installer:   {info.is_installer} ({info.installer_kind or 'none'})")
        if info.error:
            print(f"Error:       {info.error}")
    return 0 if info.valid else 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    probe = probe_system()
    if args.json:
        _print_json(probe.to_dict())
    else:
        print(f"FeatherOS Compatibility Doctor (v{__version__})")
        print(f"  Platform:         {probe.platform_system} ({probe.machine}, {probe.cpu_count} CPUs)")
        if probe.ram_total_mb is not None:
            print(f"  Memory:           {probe.ram_available_mb} MB free / {probe.ram_total_mb} MB total")
        print(f"  Wine:             {probe.wine_path or probe.wine64_path or 'NOT FOUND'}")
        print(f"  Winetricks:       {probe.winetricks_path or 'not installed'}")
        print(f"  32-bit multiarch: {'enabled' if probe.multiarch_i386 else 'not detected'}")
        vk_status = (
            f"hardware ready ({probe.vulkan_device_name})"
            if probe.vulkan_hardware_ready
            else (
                f"software only ({probe.vulkan_device_name}) — will use WineD3D"
                if probe.vulkan_software_only
                else "not detected — will use WineD3D"
            )
        )
        print(f"  Vulkan:           {vk_status}")
        print(f"  DXVK available:   {probe.dxvk_available}")
        print(f"  VKD3D available:  {probe.vkd3d_available}")
        print(f"  Recommended GPU:  {probe.recommended_graphics_backend}")
    return 0


def _cmd_bottles(args: argparse.Namespace, manager: BottleManager) -> int:
    action = args.bottle_action
    if action == "list":
        bottles = manager.list_bottles()
        if args.json:
            _print_json([b.to_dict() for b in bottles])
            return 0
        if not bottles:
            print("No bottles created yet. Run an .exe or use 'feather-run bottles create <name>'.")
            return 0
        for b in bottles:
            vd = b.virtual_desktop or "off"
            print(
                f"- {b.slug:18s} [{b.arch}, {b.windows_version}] "
                f"dxvk={b.dxvk} vkd3d={b.vkd3d} vdesktop={vd} runner={b.runner}"
            )
        return 0

    if action == "create":
        cfg = manager.create_bottle(
            args.name,
            arch=args.arch,
            windows_version=args.windows_version,
            dxvk=not args.no_dxvk,
            vkd3d=not args.no_vkd3d,
            virtual_desktop=args.virtual_desktop,
        )
        if args.json:
            _print_json(cfg.to_dict())
        else:
            print(f"Created bottle '{cfg.slug}' at {manager.bottle_dir(cfg.slug)}")
        return 0

    if action == "info":
        cfg = manager.get_bottle(args.name)
        if args.json:
            _print_json(cfg.to_dict())
        else:
            for k, v in cfg.to_dict().items():
                print(f"{k}: {v}")
        return 0

    if action == "config":
        updates: dict[str, object] = {}
        if args.windows_version is not None:
            updates["windows_version"] = args.windows_version
        if args.dxvk is not None:
            updates["dxvk"] = args.dxvk == "on"
        if args.vkd3d is not None:
            updates["vkd3d"] = args.vkd3d == "on"
        if args.gamemode is not None:
            updates["gamemode"] = args.gamemode == "on"
        if args.mangohud is not None:
            updates["mangohud"] = args.mangohud == "on"
        if args.virtual_desktop is not None:
            updates["virtual_desktop"] = (
                None if args.virtual_desktop.lower() == "off" else args.virtual_desktop
            )
        if args.dpi is not None:
            updates["dpi"] = args.dpi
        if args.runner is not None:
            updates["runner"] = args.runner
        if not updates:
            print("No configuration fields specified.", file=sys.stderr)
            return 2
        updated = manager.update_bottle(args.name, **updates)
        if not getattr(args, "dry_run", False):
            manager.apply_bottle_settings(updated.slug)
        if args.json:
            _print_json(updated.to_dict())
        else:
            print(f"Updated bottle '{updated.slug}'.")
        return 0

    if action == "delete":
        deleted = manager.delete_bottle(args.name)
        removed = prune_bottle_shortcuts(args.name)
        if not deleted:
            print(f"Bottle '{args.name}' not found.", file=sys.stderr)
            return 1
        print(f"Deleted bottle '{args.name}' (removed {len(removed)} Start Menu shortcuts).")
        return 0

    return 2


def _cmd_sync(args: argparse.Namespace, manager: BottleManager) -> int:
    if args.bottle:
        written = sync_bottle_shortcuts(manager, args.bottle)
        print(f"Synced {len(written)} shortcuts for bottle '{args.bottle}'.")
    else:
        results = sync_all_bottles(manager)
        total = sum(len(v) for v in results.values())
        print(f"Synced {total} shortcuts across {len(results)} bottles.")
    return 0


def _is_gui_session() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")) and not sys.stdin.isatty()


def _notify_desktop(title: str, body: str) -> None:
    notifier = shutil.which("notify-send")
    if notifier and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        try:
            subprocess.Popen(
                [notifier, "-a", "FeatherRun", "-i", "application-x-ms-dos-executable", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass


def _show_gui_error(title: str, body: str) -> None:
    if not _is_gui_session():
        return
    try:
        import gi  # type: ignore[import-not-found]

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk  # type: ignore[import-not-found]

        dlg = Gtk.MessageDialog(
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dlg.format_secondary_text(body)
        dlg.set_position(Gtk.WindowPosition.CENTER)
        dlg.run()
        dlg.destroy()
    except Exception:
        _notify_desktop(title, body)


def _cmd_run(args: argparse.Namespace, manager: BottleManager) -> int:
    probe = probe_system()
    plan = manager.build_launch_plan(
        args.target,
        bottle_name=args.bottle,
        isolated=args.isolated,
        extra_args=args.app_args,
        debug=args.debug,
        probe=probe,
    )

    if not plan.binary_info.valid:
        msg = f"Cannot launch {Path(args.target).name}: {plan.binary_info.error}"
        print(f"Error: {msg}", file=sys.stderr)
        _show_gui_error("FeatherRun — Unsupported File", msg)
        return 1

    if args.dry_run:
        _print_json(plan.to_dict())
        return 0

    for note in plan.notices:
        print(f"[FeatherRun] {note}", file=sys.stderr)

    if not probe.can_run_wine:
        msg = (
            "Wine is not installed on this host. "
            "Use --dry-run to inspect the launch plan or boot FeatherOS."
        )
        print(f"[FeatherRun] {msg}", file=sys.stderr)
        _show_gui_error("FeatherRun — Wine Not Found", msg)
        return 127

    is_first_run = not (plan.prefix_path / "system.reg").is_file()
    dxvk_marker = plan.prefix_path / ".featheros-dxvk-applied"
    needs_dxvk_install = (
        plan.effective_backend.startswith("dxvk")
        and shutil.which("dxvk-setup") is not None
        and not dxvk_marker.is_file()
    )
    if is_first_run or needs_dxvk_install:
        _notify_desktop(
            "Preparing Windows Environment",
            f"Configuring bottle '{plan.bottle.name}' ({plan.bottle.windows_version})...",
        )
        results = manager.apply_bottle_settings(plan.bottle.slug, probe=probe)
        if needs_dxvk_install and any("dxvk-setup" in c[0] and rc == 0 for c, rc in results):
            try:
                dxvk_marker.write_text("installed\n", encoding="utf-8")
            except OSError:
                pass
    elif _is_gui_session():
        _notify_desktop(
            "Launching Windows App",
            f"Starting {Path(args.target).name} in bottle '{plan.bottle.name}'...",
        )

    manager.touch_last_used(plan.bottle.slug)
    merged_env = os.environ.copy()
    merged_env.update(plan.env)

    proc = subprocess.run(plan.command, env=merged_env, check=False)

    if not args.no_sync:
        sync_bottle_shortcuts(manager, plan.bottle.slug)

    if proc.returncode != 0 and _is_gui_session():
        _show_gui_error(
            f"{Path(args.target).name} exited unexpectedly",
            f"Exit code {proc.returncode} in bottle '{plan.bottle.name}'.\n"
            "Try installing Visual C++ / .NET runtimes in FeatherOS Compatibility Manager, "
            "or run 'feather-run --debug' in Terminal for detailed logs.",
        )

    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feather-run",
        description="FeatherOS Windows application runner and bottle manager",
    )
    parser.add_argument("--home", help="Override FEATHEROS_HOME data directory")
    parser.add_argument("--version", action="version", version=f"feather-run {__version__}")

    subparsers = parser.add_subparsers(dest="subcommand")

    # run subcommand (also supported implicitly when passing a file path directly)
    p_run = subparsers.add_parser("run", help="Run a Windows .exe or .msi file")
    p_run.add_argument("target", help="Path to .exe or .msi binary")
    p_run.add_argument("--bottle", help="Bottle name/slug to use")
    p_run.add_argument(
        "--isolated",
        action="store_true",
        help="Automatically isolate in a dedicated bottle named after the executable",
    )
    p_run.add_argument("--dry-run", action="store_true", help="Print resolved JSON launch plan only")
    p_run.add_argument("--no-sync", action="store_true", help="Skip Start Menu shortcut sync")
    p_run.add_argument("--debug", action="store_true", help="Enable verbose Wine debug logging")
    p_run.add_argument("app_args", nargs=argparse.REMAINDER, help="Arguments passed to the Windows app")

    # inspect subcommand
    p_inspect = subparsers.add_parser("inspect", help="Inspect a Windows PE or MSI binary")
    p_inspect.add_argument("target", help="Path to .exe, .dll, or .msi file")
    p_inspect.add_argument("--json", action="store_true", help="Output JSON")

    # doctor subcommand
    p_doc = subparsers.add_parser("doctor", help="Check Wine, multiarch, and Vulkan readiness")
    p_doc.add_argument("--json", action="store_true", help="Output JSON")

    # sync subcommand
    p_sync = subparsers.add_parser("sync", help="Sync Windows Start Menu shortcuts to FeatherShell")
    p_sync.add_argument("bottle", nargs="?", help="Optional bottle slug (defaults to all)")

    # bottles subcommand
    p_bottles = subparsers.add_parser("bottles", help="Manage isolated Windows compatibility bottles")
    b_sub = p_bottles.add_subparsers(dest="bottle_action", required=True)

    b_list = b_sub.add_parser("list", help="List bottles")
    b_list.add_argument("--json", action="store_true")

    b_create = b_sub.add_parser("create", help="Create a new bottle")
    b_create.add_argument("name")
    b_create.add_argument("--arch", choices=VALID_ARCHES, default="win64")
    b_create.add_argument("--windows-version", choices=VALID_WINDOWS_VERSIONS, default="win10")
    b_create.add_argument("--no-dxvk", action="store_true")
    b_create.add_argument("--no-vkd3d", action="store_true")
    b_create.add_argument("--virtual-desktop", help="e.g. 1280x720")
    b_create.add_argument("--json", action="store_true")

    b_info = b_sub.add_parser("info", help="Show bottle settings")
    b_info.add_argument("name")
    b_info.add_argument("--json", action="store_true")

    b_cfg = b_sub.add_parser("config", help="Update bottle settings")
    b_cfg.add_argument("name")
    b_cfg.add_argument("--windows-version", choices=VALID_WINDOWS_VERSIONS)
    b_cfg.add_argument("--dxvk", choices=("on", "off"))
    b_cfg.add_argument("--vkd3d", choices=("on", "off"))
    b_cfg.add_argument("--gamemode", choices=("on", "off"))
    b_cfg.add_argument("--mangohud", choices=("on", "off"))
    b_cfg.add_argument("--virtual-desktop", help="WIDTHxHEIGHT or 'off'")
    b_cfg.add_argument("--dpi", type=int)
    b_cfg.add_argument("--runner")
    b_cfg.add_argument("--json", action="store_true")

    b_del = b_sub.add_parser("delete", help="Delete a bottle and its shortcuts")
    b_del.add_argument("name")

    return parser


KNOWN_SUBCOMMANDS = {"run", "inspect", "doctor", "sync", "bottles"}


def _normalize_argv(argv: list[str]) -> list[str]:
    """Allow `feather-run app.exe` shorthand for desktop MIME double-click invocation."""
    if not argv:
        return argv
    # Find first positional token (skipping global --home VALUE)
    idx = 0
    while idx < len(argv):
        tok = argv[idx]
        if tok == "--home":
            idx += 2
            continue
        if tok.startswith("--home="):
            idx += 1
            continue
        if tok in ("-h", "--help", "--version"):
            return argv
        if tok.startswith("-"):
            # Flags like `--bottle foo app.exe` imply `run`
            return argv[:idx] + ["run"] + argv[idx:]
        if tok not in KNOWN_SUBCOMMANDS:
            return argv[:idx] + ["run"] + argv[idx:]
        return argv
    return argv


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    normalized = _normalize_argv(raw_argv)
    parser = build_parser()
    args = parser.parse_args(normalized)

    if not args.subcommand:
        parser.print_help()
        return 0

    manager = BottleManager(home=args.home)

    if args.subcommand == "inspect":
        return _cmd_inspect(args)
    if args.subcommand == "doctor":
        return _cmd_doctor(args)
    if args.subcommand == "bottles":
        return _cmd_bottles(args, manager)
    if args.subcommand == "sync":
        return _cmd_sync(args, manager)
    if args.subcommand == "run":
        if args.app_args and args.app_args[0] == "--":
            args.app_args = args.app_args[1:]
        return _cmd_run(args, manager)

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
