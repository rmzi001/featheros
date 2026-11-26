"""feather-settings: Windows 11-style Unified System Settings Hub for FeatherOS.

Provides one clean sidebar-driven Settings interface for Display, Sound, Wi-Fi,
Bluetooth, Power, Personalization, Performance Profiles, Windows Compatibility,
and System Updates without hunting through scattered Linux dialogs.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Callable, Sequence

from . import __codename__, __version__
from .ctl import PROFILES, apply_profile, collect_system_status, get_active_profile
from .fluent_theme import apply_fluent_gtk_theme
from .system_probe import SystemProbe, probe_system


@dataclass(frozen=True)
class SettingsAction:
    """Single clickable card inside a FeatherOS Settings section."""

    id: str
    section: str
    title: str
    description: str
    command: tuple[str, ...]
    check_binary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SECTIONS: tuple[tuple[str, str], ...] = (
    ("system", "System"),
    ("network", "Network & Internet"),
    ("devices", "Bluetooth & Devices"),
    ("personalization", "Personalization"),
    ("sound", "Sound"),
    ("windows", "Windows Apps"),
    ("updates", "Apps & Updates"),
)

SETTINGS_ACTIONS: tuple[SettingsAction, ...] = (
    # System
    SettingsAction(
        id="display",
        section="system",
        title="Display & Resolution",
        description="Resolution, refresh rate, scale, and multi-monitor arrangement.",
        command=("xfce4-display-settings",),
        check_binary="xfce4-display-settings",
    ),
    SettingsAction(
        id="power",
        section="system",
        title="Power & Battery",
        description="Screen timeout, sleep behavior, lid action, and battery indicator.",
        command=("xfce4-power-manager-settings",),
        check_binary="xfce4-power-manager-settings",
    ),
    SettingsAction(
        id="taskmanager",
        section="system",
        title="Live Task Manager",
        description="Real-time CPU & RAM graphs, running apps, and End Task (Ctrl+Shift+Esc).",
        command=("xfce4-taskmanager",),
        check_binary="xfce4-taskmanager",
    ),
    SettingsAction(
        id="notifications",
        section="system",
        title="Notifications & Do Not Disturb",
        description="Configure alert popups, duration, and Do Not Disturb mode.",
        command=("xfce4-notifyd-config",),
        check_binary="xfce4-notifyd-config",
    ),
    # Network
    SettingsAction(
        id="wifi",
        section="network",
        title="Wi-Fi, Ethernet & VPN",
        description="Manage wireless networks, static IPs, DNS, and VPN profiles.",
        command=("nm-connection-editor",),
        check_binary="nm-connection-editor",
    ),
    # Bluetooth & Devices
    SettingsAction(
        id="bluetooth",
        section="devices",
        title="Bluetooth Devices",
        description="Pair headphones, controllers, keyboards, and mice.",
        command=("blueman-manager",),
        check_binary="blueman-manager",
    ),
    SettingsAction(
        id="mouse",
        section="devices",
        title="Mouse & Touchpad",
        description="Pointer speed, natural scrolling, tap-to-click, and sensitivity.",
        command=("xfce4-mouse-settings",),
        check_binary="xfce4-mouse-settings",
    ),
    SettingsAction(
        id="keyboard",
        section="devices",
        title="Keyboard & Shortcuts",
        description="Layouts, repeat rate, and Windows-style hotkey bindings.",
        command=("xfce4-keyboard-settings",),
        check_binary="xfce4-keyboard-settings",
    ),
    # Personalization
    SettingsAction(
        id="appearance",
        section="personalization",
        title="Theme, Icons & Fonts",
        description="Switch Fluent Dark/Light theme, Papirus icons, and UI fonts.",
        command=("xfce4-appearance-settings",),
        check_binary="xfce4-appearance-settings",
    ),
    SettingsAction(
        id="wallpaper",
        section="personalization",
        title="Background & Desktop Icons",
        description="Choose wallpaper, icon size, and desktop shortcuts.",
        command=("xfdesktop-settings",),
        check_binary="xfdesktop-settings",
    ),
    SettingsAction(
        id="taskbar",
        section="personalization",
        title="Taskbar & Start Menu",
        description="Customize centered Windows 11 taskbar, height, auto-hide, and plugins.",
        command=("xfce4-panel", "--preferences"),
        check_binary="xfce4-panel",
    ),
    SettingsAction(
        id="windows-wm",
        section="personalization",
        title="Window Borders & Snapping",
        description="Window style, titlebar buttons, shadows, and edge snapping.",
        command=("xfwm4-settings",),
        check_binary="xfwm4-settings",
    ),
    # Sound
    SettingsAction(
        id="sound",
        section="sound",
        title="Volume, Speakers & Microphone",
        description="Select output device, adjust per-app volume, and test microphone.",
        command=("pavucontrol",),
        check_binary="pavucontrol",
    ),
    # Windows Apps (FeatherRun)
    SettingsAction(
        id="compat-mgr",
        section="windows",
        title="FeatherOS Compatibility Manager",
        description="Manage Windows .exe/.msi bottles, DXVK/Vulkan, runtimes, and GE-Proton.",
        command=("feather-compat",),
        check_binary="feather-compat",
    ),
    SettingsAction(
        id="windows-c",
        section="windows",
        title="Open Windows C: Drive",
        description="Browse Program Files and installed Windows apps in File Explorer.",
        command=("thunar", str(Path.home() / "Windows-C")),
        check_binary="thunar",
    ),
    SettingsAction(
        id="sync-apps",
        section="windows",
        title="Sync Windows Start Menu Shortcuts",
        description="Scan all FeatherOS bottles and refresh Windows apps in the Start Menu.",
        command=("feather-run", "sync"),
        check_binary="feather-run",
    ),
    # Apps & Updates
    SettingsAction(
        id="store",
        section="updates",
        title="FeatherStore — App & Gaming Hub",
        description="Install browsers, Steam + Proton, Lutris, LibreOffice, VLC, and dev tools.",
        command=("feather-store",),
        check_binary="feather-store",
    ),
    SettingsAction(
        id="system-update",
        section="updates",
        title="Check for System Updates",
        description="Refresh Debian security updates and Wine/Mesa packages.",
        command=(
            "xfce4-terminal",
            "-e",
            "sh -c 'sudo apt-get update && sudo apt-get upgrade; read -p \"Done. Press Enter...\"'",
        ),
        check_binary="apt-get",
    ),
    SettingsAction(
        id="install-disk",
        section="updates",
        title="Install FeatherOS to Disk",
        description="Launch the Calamares graphical installer to install FeatherOS permanently.",
        command=("pkexec", "calamares"),
        check_binary="calamares",
    ),
)


class SettingsController:
    """Headless controller for FeatherOS Unified Settings."""

    def __init__(
        self,
        *,
        home: str | Path | None = None,
        config_dir: str | Path | None = None,
        which: Callable[[str], str | None] = shutil.which,
        probe: SystemProbe | None = None,
    ) -> None:
        self.home = home
        self.config_dir = config_dir
        self.which = which
        self.probe = probe or probe_system(which=which)

    def list_sections(self) -> list[dict[str, str]]:
        return [{"id": sid, "label": label} for sid, label in SECTIONS]

    def list_actions(self, section: str | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for action in SETTINGS_ACTIONS:
            if section and action.section != section:
                continue
            item = action.to_dict()
            item["available"] = (
                True if action.check_binary is None else self.which(action.check_binary) is not None
            )
            results.append(item)
        return results

    def get_action(self, action_id: str) -> SettingsAction:
        for action in SETTINGS_ACTIONS:
            if action.id == action_id:
                return action
        raise KeyError(f"Unknown settings action '{action_id}'")

    def run_action(self, action_id: str, *, dry_run: bool = False) -> tuple[bool, str]:
        action = self.get_action(action_id)
        cmd = list(action.command)
        if dry_run:
            return True, f"[dry-run] {' '.join(cmd)}"
        if action.check_binary and self.which(action.check_binary) is None:
            return (
                False,
                f"'{action.check_binary}' is not installed on this host (preview mode; works natively in FeatherOS).",
            )
        subprocess.Popen(cmd)
        return True, f"Opened {action.title}."

    def set_profile(self, profile_name: str, *, dry_run: bool = False) -> dict[str, Any]:
        return apply_profile(profile_name, config_dir=self.config_dir, dry_run=dry_run)

    def summary(self) -> dict[str, Any]:
        status = collect_system_status(
            home=self.home, config_dir=self.config_dir, probe=self.probe
        )
        status["codename"] = __codename__
        status["sections"] = self.list_sections()
        return status


def _run_gtk_settings(controller: SettingsController) -> int:
    import gi  # type: ignore[import-not-found]

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # type: ignore[import-not-found]

    apply_fluent_gtk_theme()

    class FeatherSettingsWindow(Gtk.Window):
        def __init__(self) -> None:
            super().__init__(title=f"Settings — FeatherOS v{__version__}")
            self.set_default_size(940, 600)
            self.set_border_width(14)

            outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            self.add(outer)

            # Left Sidebar (Windows 11 Settings style)
            sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            sidebar_box.set_size_request(230, -1)
            outer.pack_start(sidebar_box, False, False, 0)

            brand = Gtk.Label(xalign=0)
            brand.set_markup(
                f"<b><big>Settings</big></b>\n<small>FeatherOS v{__version__} ({__codename__})</small>"
            )
            sidebar_box.pack_start(brand, False, False, 0)

            self.nav_list = Gtk.ListBox()
            self.nav_list.connect("row-selected", self._on_section_selected)
            for sid, label in SECTIONS:
                row = Gtk.ListBoxRow()
                row.section_id = sid  # type: ignore[attr-defined]
                lbl = Gtk.Label(label=label, xalign=0)
                lbl.set_margin_start(6)
                row.add(lbl)
                self.nav_list.add(row)
            sidebar_box.pack_start(self.nav_list, True, True, 0)

            # Right Detail Area
            right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            outer.pack_start(right_box, True, True, 0)

            self.section_header = Gtk.Label(xalign=0)
            self.section_header.get_style_context().add_class("feather-title")
            right_box.pack_start(self.section_header, False, False, 0)

            scroll = Gtk.ScrolledWindow()
            scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            right_box.pack_start(scroll, True, True, 0)

            self.cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            scroll.add(self.cards_box)

            self.status_lbl = Gtk.Label(label="Ready.", xalign=0)
            self.status_lbl.get_style_context().add_class("feather-subtitle")
            right_box.pack_start(self.status_lbl, False, False, 0)

            first_row = self.nav_list.get_row_at_index(0)
            if first_row is not None:
                self.nav_list.select_row(first_row)

        def _on_section_selected(self, _box: Any, row: Any) -> None:
            if row is None or not hasattr(row, "section_id"):
                return
            self._render_section(row.section_id)

        def _render_section(self, section_id: str) -> None:
            for child in self.cards_box.get_children():
                self.cards_box.remove(child)

            sec_label = dict(SECTIONS).get(section_id, section_id.title())
            self.section_header.set_markup(f"<b><big>{sec_label}</big></b>")

            if section_id == "system":
                st = controller.summary()
                sys_info = st["system"]
                prof = st["active_profile"]
                ram_text = (
                    f"{sys_info['ram_available_mb']} MB free / {sys_info['ram_total_mb']} MB total"
                    if sys_info["ram_total_mb"] is not None
                    else "Detected at runtime"
                )
                banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                banner.get_style_context().add_class("feather-card")
                info_lbl = Gtk.Label(xalign=0)
                info_lbl.set_markup(
                    f"<b>FeatherOS {__version__} (Plume Fluent)</b>\n"
                    f"<small>CPUs: {sys_info['cpu_count']}  •  Memory: {ram_text}  •  "
                    f"Profile: {prof['label']}  •  Bottles: {st['bottles_count']}</small>"
                )
                banner.pack_start(info_lbl, False, False, 0)

                p_row = Gtk.Box(spacing=8)
                for key, p in PROFILES.items():
                    btn = Gtk.Button(label=p.label)
                    if key == prof["name"]:
                        btn.get_style_context().add_class("feather-primary")
                    btn.connect("clicked", self._on_profile, key)
                    p_row.pack_start(btn, False, False, 0)
                banner.pack_start(p_row, False, False, 0)
                self.cards_box.pack_start(banner, False, False, 0)

            for item in controller.list_actions(section=section_id):
                card = Gtk.Box(spacing=12)
                card.get_style_context().add_class("feather-card")
                txt = Gtk.Label(xalign=0)
                txt.set_markup(f"<b>{item['title']}</b>\n<small>{item['description']}</small>")
                btn = Gtk.Button(label="Open")
                btn.connect("clicked", self._on_open_action, item["id"])
                card.pack_start(txt, True, True, 0)
                card.pack_end(btn, False, False, 0)
                self.cards_box.pack_start(card, False, False, 0)

            self.cards_box.show_all()

        def _on_open_action(self, _btn: Any, action_id: str) -> None:
            _ok, msg = controller.run_action(action_id)
            self.status_lbl.set_text(msg)

        def _on_profile(self, _btn: Any, key: str) -> None:
            controller.set_profile(key)
            self._render_section("system")
            self.status_lbl.set_text(f"Active performance profile set to '{key}'.")

    win = FeatherSettingsWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def _run_tk_settings(controller: SettingsController) -> int:
    import tkinter as tk
    from tkinter import ttk

    bg = "#141821"
    sidebar_bg = "#10141c"
    card_bg = "#1c2230"
    fg = "#f8fafc"
    muted = "#94a3b8"
    accent = "#38bdf8"

    root = tk.Tk()
    root.title(f"Settings — FeatherOS v{__version__}")
    root.geometry("920x580")
    root.configure(bg=bg)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=bg)
    style.configure("Side.TFrame", background=sidebar_bg)
    style.configure("Card.TFrame", background=card_bg)
    style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("Title.TLabel", background=bg, foreground=fg, font=("Segoe UI", 15, "bold"))
    style.configure("SideTitle.TLabel", background=sidebar_bg, foreground=accent, font=("Segoe UI", 13, "bold"))
    style.configure("SideMuted.TLabel", background=sidebar_bg, foreground=muted, font=("Segoe UI", 9))
    style.configure("CardTitle.TLabel", background=card_bg, foreground=fg, font=("Segoe UI", 10, "bold"))
    style.configure("CardMuted.TLabel", background=card_bg, foreground=muted, font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
    style.configure("TButton", background="#242c3d", foreground=fg, padding=(12, 6), borderwidth=1)
    style.map("TButton", background=[("active", "#2e3950"), ("pressed", "#0284c7")])

    outer = ttk.Frame(root)
    outer.pack(fill="both", expand=True)

    side = ttk.Frame(outer, style="Side.TFrame", padding=14, width=230)
    side.pack(side="left", fill="y")
    side.pack_propagate(False)

    ttk.Label(side, text="Settings", style="SideTitle.TLabel").pack(anchor="w")
    ttk.Label(side, text=f"FeatherOS v{__version__} (Plume Fluent)", style="SideMuted.TLabel").pack(anchor="w", pady=(0, 12))

    nav = tk.Listbox(
        side,
        bg=sidebar_bg,
        fg=fg,
        selectbackground="#0284c7",
        selectforeground="#ffffff",
        highlightthickness=0,
        borderwidth=0,
        font=("Segoe UI", 10),
        activestyle="none",
    )
    for _sid, label in SECTIONS:
        nav.insert(tk.END, f"  {label}")
    nav.pack(fill="both", expand=True)

    right = ttk.Frame(outer, padding=16)
    right.pack(side="left", fill="both", expand=True)

    title_var = tk.StringVar(value="System")
    ttk.Label(right, textvariable=title_var, style="Title.TLabel").pack(anchor="w", pady=(0, 10))

    cards_container = ttk.Frame(right)
    cards_container.pack(fill="both", expand=True)

    status_var = tk.StringVar(value="Ready.")
    ttk.Label(right, textvariable=status_var, style="Muted.TLabel", padding=(0, 8, 0, 0)).pack(anchor="w")

    def render_section(idx: int) -> None:
        sid, label = SECTIONS[idx]
        title_var.set(label)
        for w in cards_container.winfo_children():
            w.destroy()

        if sid == "system":
            prof = get_active_profile(controller.config_dir)
            top = ttk.Frame(cards_container, style="Card.TFrame", padding=12)
            top.pack(fill="x", pady=(0, 8))
            ttk.Label(top, text=f"Performance Profile: {prof.label}", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(top, text=prof.description, style="CardMuted.TLabel").pack(anchor="w", pady=(2, 8))
            prow = ttk.Frame(top, style="Card.TFrame")
            prow.pack(anchor="w")
            for k, p in PROFILES.items():
                ttk.Button(
                    prow,
                    text=p.label,
                    command=lambda key=k: (
                        controller.set_profile(key),
                        status_var.set(f"Switched profile to {key}."),
                        render_section(0),
                    ),
                ).pack(side="left", padx=(0, 8))

        for item in controller.list_actions(section=sid):
            card = ttk.Frame(cards_container, style="Card.TFrame", padding=12)
            card.pack(fill="x", pady=4)
            left_txt = ttk.Frame(card, style="Card.TFrame")
            left_txt.pack(side="left", fill="x", expand=True)
            ttk.Label(left_txt, text=item["title"], style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(left_txt, text=item["description"], style="CardMuted.TLabel").pack(anchor="w")
            ttk.Button(
                card,
                text="Open",
                command=lambda aid=item["id"]: status_var.set(controller.run_action(aid)[1]),
            ).pack(side="right", padx=(10, 0))

    def on_nav(_evt: Any) -> None:
        sel = nav.curselection()
        if sel:
            render_section(sel[0])

    nav.bind("<<ListboxSelect>>", on_nav)
    nav.selection_set(0)
    render_section(0)
    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feather-settings",
        description="FeatherOS Windows-style Unified Settings Hub",
    )
    parser.add_argument("--home", help="Override FEATHEROS_HOME data directory")
    parser.add_argument("--config-dir", help="Override FeatherOS config directory")
    parser.add_argument("--version", action="version", version=f"feather-settings {__version__}")

    sub = parser.add_subparsers(dest="command")
    p_list = sub.add_parser("list", help="List settings sections and cards")
    p_list.add_argument("--section", choices=[s[0] for s in SECTIONS])
    p_list.add_argument("--json", action="store_true")

    p_open = sub.add_parser("open", help="Open a specific settings module")
    p_open.add_argument("action_id")
    p_open.add_argument("--dry-run", action="store_true")

    p_gui = sub.add_parser("gui", help="Launch Unified Settings GUI")
    p_gui.add_argument("--toolkit", choices=("auto", "gtk", "tk"), default="auto")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    controller = SettingsController(home=args.home, config_dir=args.config_dir)

    if not args.command or args.command == "gui":
        toolkit = getattr(args, "toolkit", "auto")
        if toolkit in ("auto", "gtk"):
            try:
                return _run_gtk_settings(controller)
            except ImportError:
                if toolkit == "gtk":
                    print("Error: PyGObject (GTK3) is not installed.", file=sys.stderr)
                    return 1
        return _run_tk_settings(controller)

    if args.command == "list":
        items = controller.list_actions(section=args.section)
        if args.json:
            print(json.dumps(items, indent=2))
        else:
            for item in items:
                print(f"- {item['id']:15s} [{item['section']:15s}] {item['title']}")
        return 0

    if args.command == "open":
        ok, msg = controller.run_action(args.action_id, dry_run=args.dry_run)
        print(msg)
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
