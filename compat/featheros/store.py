"""feather-store: FeatherOS Welcome, Browser & Gaming App Hub.

Provides a lightweight curated catalog for one-click installation of web browsers,
PC gaming launchers (Steam/Heroic/Lutris/GE-Proton), productivity apps, and
developer tools, plus quick access to FeatherRun and the Calamares disk installer.
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

from . import __version__
from .ctl import collect_system_status
from .runners import list_installed_runners
from .system_probe import SystemProbe, probe_system


@dataclass(frozen=True)
class StoreApp:
    """Single installable application or stack in FeatherStore."""

    id: str
    name: str
    category: str  # "browsers", "gaming", "productivity", "developer"
    summary: str
    install_kind: str  # "apt", "ge-proton", "script"
    packages: tuple[str, ...]
    check_binaries: tuple[str, ...]
    size_hint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CATALOG: tuple[StoreApp, ...] = (
    # Browsers
    StoreApp(
        id="firefox-esr",
        name="Firefox ESR",
        category="browsers",
        summary="Fast, privacy-respecting web browser with low idle footprint.",
        install_kind="apt",
        packages=("firefox-esr",),
        check_binaries=("firefox-esr", "firefox"),
        size_hint="~260 MB",
    ),
    StoreApp(
        id="chromium",
        name="Chromium",
        category="browsers",
        summary="Lightweight open-source Chrome-compatible web browser.",
        install_kind="apt",
        packages=("chromium",),
        check_binaries=("chromium", "chromium-browser"),
        size_hint="~310 MB",
    ),
    # Gaming & Windows Compatibility
    StoreApp(
        id="steam",
        name="Steam + Proton",
        category="gaming",
        summary="PC gaming store with built-in Proton compatibility for Windows games.",
        install_kind="apt",
        packages=("steam-installer",),
        check_binaries=("steam",),
        size_hint="~500 MB",
    ),
    StoreApp(
        id="lutris",
        name="Lutris Game Manager",
        category="gaming",
        summary="Unified launcher for Windows PC games, GOG, Epic, and emulators.",
        install_kind="apt",
        packages=("lutris",),
        check_binaries=("lutris",),
        size_hint="~90 MB",
    ),
    StoreApp(
        id="ge-proton",
        name="GE-Proton Latest Runner",
        category="gaming",
        summary="Community-patched Proton runner with extra game & codec fixes for FeatherRun.",
        install_kind="ge-proton",
        packages=(),
        check_binaries=(),
        size_hint="~450 MB",
    ),
    StoreApp(
        id="gaming-perf",
        name="GameMode + MangoHud",
        category="gaming",
        summary="CPU boost daemon and lightweight Vulkan/OpenGL FPS overlay.",
        install_kind="apt",
        packages=("gamemode", "mangohud"),
        check_binaries=("gamemoderun", "mangohud"),
        size_hint="~25 MB",
    ),
    # Productivity
    StoreApp(
        id="libreoffice",
        name="LibreOffice Suite",
        category="productivity",
        summary="Full Microsoft Office (.docx, .xlsx, .pptx) compatible office suite.",
        install_kind="apt",
        packages=("libreoffice-writer", "libreoffice-calc", "libreoffice-impress"),
        check_binaries=("libreoffice", "soffice"),
        size_hint="~480 MB",
    ),
    StoreApp(
        id="vlc",
        name="VLC Media Player",
        category="productivity",
        summary="Plays virtually any audio or video format with hardware decoding.",
        install_kind="apt",
        packages=("vlc",),
        check_binaries=("vlc",),
        size_hint="~120 MB",
    ),
    StoreApp(
        id="gimp",
        name="GIMP Image Editor",
        category="productivity",
        summary="Full-featured raster image & PSD editor.",
        install_kind="apt",
        packages=("gimp",),
        check_binaries=("gimp",),
        size_hint="~220 MB",
    ),
    # Developer Tools
    StoreApp(
        id="dev-essentials",
        name="Developer Essentials",
        category="developer",
        summary="Git, GCC/build-essential, Python venv/pip, curl, and ripgrep.",
        install_kind="apt",
        packages=("git", "build-essential", "python3-venv", "python3-pip", "ripgrep"),
        check_binaries=("git", "gcc", "rg"),
        size_hint="~280 MB",
    ),
    StoreApp(
        id="nodejs",
        name="Node.js & npm",
        category="developer",
        summary="JavaScript runtime and package manager for modern web & CLI tools.",
        install_kind="apt",
        packages=("nodejs", "npm"),
        check_binaries=("node", "npm"),
        size_hint="~110 MB",
    ),
)

VALID_CATEGORIES = ("browsers", "gaming", "productivity", "developer")


@dataclass(frozen=True)
class InstallPlan:
    """Resolved installation plan for a FeatherStore item."""

    app: StoreApp
    installed: bool
    command: list[str]
    can_execute_locally: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "app": self.app.to_dict(),
            "installed": self.installed,
            "command": self.command,
            "can_execute_locally": self.can_execute_locally,
            "note": self.note,
        }


class StoreController:
    """Headless FeatherStore catalog, status detector, and install planner."""

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

    def list_apps(self, category: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for app in CATALOG:
            if category and app.category != category:
                continue
            entry = app.to_dict()
            entry["installed"] = self.is_installed(app)
            items.append(entry)
        return items

    def get_app(self, app_id: str) -> StoreApp:
        for app in CATALOG:
            if app.id == app_id:
                return app
        raise KeyError(f"Unknown FeatherStore app id '{app_id}'")

    def is_installed(self, app: StoreApp) -> bool:
        if app.install_kind == "ge-proton":
            runners = list_installed_runners(home=self.home)
            return any(r.kind == "ge-proton" for r in runners)
        if not app.check_binaries:
            return False
        return any(self.which(binary) is not None for binary in app.check_binaries)

    def has_calamares_installer(self) -> bool:
        return self.which("calamares") is not None

    def build_install_plan(self, app_id: str) -> InstallPlan:
        app = self.get_app(app_id)
        installed = self.is_installed(app)

        if app.install_kind == "ge-proton":
            cmd = ["feather-ctl", "runners"]
            return InstallPlan(
                app=app,
                installed=installed,
                command=cmd,
                can_execute_locally=True,
                note="Downloads latest GE-Proton release tarball into FEATHEROS_HOME/runners.",
            )

        apt_get = self.which("apt-get")
        pkexec = self.which("pkexec")
        sudo = self.which("sudo")
        prefix: list[str] = []
        if pkexec:
            prefix = [pkexec]
        elif sudo:
            prefix = [sudo]

        cmd = prefix + ["apt-get", "install", "-y", "--no-install-recommends", *app.packages]
        can_run = apt_get is not None
        note = (
            f"Will install Debian packages: {', '.join(app.packages)}"
            if can_run
            else "apt-get is not available on this host (preview mode; runs natively inside FeatherOS)."
        )
        return InstallPlan(
            app=app,
            installed=installed,
            command=cmd,
            can_execute_locally=can_run,
            note=note,
        )

    def install_app(self, app_id: str, *, dry_run: bool = False) -> tuple[InstallPlan, bool, str]:
        plan = self.build_install_plan(app_id)
        if dry_run:
            return plan, True, f"[dry-run] {' '.join(plan.command)}"
        if not plan.can_execute_locally:
            return plan, False, plan.note
        if plan.app.install_kind == "ge-proton":
            return plan, False, "Use GitHub GE-Proton downloader on a live FeatherOS session."
        subprocess.Popen(plan.command)
        return plan, True, f"Started installer for {plan.app.name}."

    def welcome_summary(self) -> dict[str, Any]:
        status = collect_system_status(
            home=self.home, config_dir=self.config_dir, probe=self.probe
        )
        status["calamares_available"] = self.has_calamares_installer()
        status["catalog_count"] = len(CATALOG)
        return status


def _run_gtk_store(controller: StoreController) -> int:
    import gi  # type: ignore[import-not-found]

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # type: ignore[import-not-found]

    class FeatherStoreWindow(Gtk.Window):
        def __init__(self) -> None:
            super().__init__(title=f"Welcome to FeatherOS v{__version__} — App Hub")
            self.set_default_size(840, 540)
            self.set_border_width(14)

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(root)

            title = Gtk.Label(xalign=0)
            title.set_markup(
                f"<b><big>Welcome to FeatherOS</big></b>  <small>v{__version__} (Plume)</small>\n"
                "<small>Lightweight Debian desktop with built-in Windows .exe/.msi compatibility.</small>"
            )
            root.pack_start(title, False, False, 0)

            quick = Gtk.Box(spacing=8)
            btn_compat = Gtk.Button(label="Open Compatibility Manager")
            btn_compat.connect("clicked", lambda _b: subprocess.Popen(["feather-compat"]))
            quick.pack_start(btn_compat, False, False, 0)
            if controller.has_calamares_installer():
                btn_install = Gtk.Button(label="Install FeatherOS to Disk")
                btn_install.connect("clicked", lambda _b: subprocess.Popen(["pkexec", "calamares"]))
                quick.pack_start(btn_install, False, False, 0)
            root.pack_start(quick, False, False, 0)

            notebook = Gtk.Notebook()
            root.pack_start(notebook, True, True, 0)

            self.status_lbl = Gtk.Label(label="Choose an app to install.", xalign=0)
            root.pack_start(self.status_lbl, False, False, 0)

            for cat in VALID_CATEGORIES:
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
                box.set_border_width(10)
                for item in controller.list_apps(category=cat):
                    row = Gtk.Box(spacing=10)
                    badge = " [Installed]" if item["installed"] else f" ({item['size_hint']})"
                    lbl = Gtk.Label(xalign=0)
                    lbl.set_markup(f"<b>{item['name']}</b><small>{badge}</small>\n<small>{item['summary']}</small>")
                    btn = Gtk.Button(label="Installed" if item["installed"] else "Install")
                    btn.set_sensitive(not item["installed"])
                    btn.connect("clicked", self._on_install, item["id"])
                    row.pack_start(lbl, True, True, 0)
                    row.pack_end(btn, False, False, 0)
                    box.pack_start(row, False, False, 0)
                notebook.append_page(box, Gtk.Label(label=cat.title()))

        def _on_install(self, _btn: Any, app_id: str) -> None:
            _plan, _ok, msg = controller.install_app(app_id)
            self.status_lbl.set_text(msg)

    win = FeatherStoreWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def _run_tk_store(controller: StoreController) -> int:
    import tkinter as tk
    from tkinter import ttk

    bg = "#0f172a"
    panel = "#1e293b"
    fg = "#f8fafc"
    muted = "#94a3b8"
    accent = "#38bdf8"

    root = tk.Tk()
    root.title(f"Welcome to FeatherOS v{__version__} — FeatherStore")
    root.geometry("860x540")
    root.configure(bg=bg)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=panel)
    style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=panel, foreground=fg, font=("Segoe UI", 10, "bold"))
    style.configure("CardMuted.TLabel", background=panel, foreground=muted, font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=bg, foreground=accent, font=("Segoe UI", 14, "bold"))
    style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
    style.configure("TButton", background=panel, foreground=fg, padding=6, borderwidth=1)
    style.map("TButton", background=[("active", "#334155"), ("pressed", "#0284c7")])
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=panel, foreground=muted, padding=(14, 7))
    style.map(
        "TNotebook.Tab",
        background=[("selected", "#0284c7"), ("active", "#334155")],
        foreground=[("selected", "#ffffff"), ("active", "#f8fafc")],
    )

    header = ttk.Frame(root, padding=14)
    header.pack(fill="x")
    ttk.Label(header, text="Welcome to FeatherOS — App Hub", style="Title.TLabel").pack(anchor="w")
    ttk.Label(
        header,
        text=f"v{__version__} (Plume)  •  One-click Browsers, Gaming Launchers, Productivity & Dev Tools",
        style="Muted.TLabel",
    ).pack(anchor="w", pady=(2, 0))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=14, pady=6)

    status_var = tk.StringVar(value="Select any app to preview or start installation.")
    ttk.Label(root, textvariable=status_var, style="Muted.TLabel", padding=(14, 8)).pack(fill="x")

    for cat in VALID_CATEGORIES:
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text=cat.title())
        for item in controller.list_apps(category=cat):
            card = ttk.Frame(tab, style="Card.TFrame", padding=10)
            card.pack(fill="x", pady=5)
            left = ttk.Frame(card, style="Card.TFrame")
            left.pack(side="left", fill="x", expand=True)
            badge = "Installed" if item["installed"] else item["size_hint"]
            ttk.Label(left, text=f"{item['name']}  ({badge})", style="Card.TLabel").pack(anchor="w")
            ttk.Label(left, text=item["summary"], style="CardMuted.TLabel").pack(anchor="w")
            btn = ttk.Button(
                card,
                text="Installed" if item["installed"] else "Install",
                command=lambda aid=item["id"]: status_var.set(controller.install_app(aid)[2]),
            )
            if item["installed"]:
                btn.state(["disabled"])
            btn.pack(side="right", padx=(8, 0))

    root.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feather-store",
        description="FeatherOS Welcome & Curated App Hub",
    )
    parser.add_argument("--home", help="Override FEATHEROS_HOME data directory")
    parser.add_argument("--version", action="version", version=f"feather-store {__version__}")

    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List curated FeatherStore apps")
    p_list.add_argument("--category", choices=VALID_CATEGORIES)
    p_list.add_argument("--json", action="store_true")

    p_plan = sub.add_parser("plan", help="Show resolved installation plan for an app")
    p_plan.add_argument("app_id")
    p_plan.add_argument("--json", action="store_true")

    p_inst = sub.add_parser("install", help="Install an app from FeatherStore")
    p_inst.add_argument("app_id")
    p_inst.add_argument("--dry-run", action="store_true")

    p_gui = sub.add_parser("gui", help="Launch FeatherStore Welcome GUI")
    p_gui.add_argument("--toolkit", choices=("auto", "gtk", "tk"), default="auto")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    controller = StoreController(home=args.home)

    if not args.command or args.command == "gui":
        toolkit = getattr(args, "toolkit", "auto")
        if toolkit in ("auto", "gtk"):
            try:
                return _run_gtk_store(controller)
            except ImportError:
                if toolkit == "gtk":
                    print("Error: PyGObject (GTK3) is not installed.", file=sys.stderr)
                    return 1
        return _run_tk_store(controller)

    if args.command == "list":
        apps = controller.list_apps(category=args.category)
        if args.json:
            print(json.dumps(apps, indent=2))
        else:
            for a in apps:
                state = "installed" if a["installed"] else a["size_hint"]
                print(f"- {a['id']:16s} [{a['category']:12s}] {a['name']} ({state})")
        return 0

    if args.command == "plan":
        plan = controller.build_install_plan(args.app_id)
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            print(f"App:     {plan.app.name} ({plan.app.id})")
            print(f"Command: {' '.join(plan.command)}")
            print(f"Note:    {plan.note}")
        return 0

    if args.command == "install":
        _plan, ok, msg = controller.install_app(args.app_id, dry_run=args.dry_run)
        print(msg)
        return 0 if ok else 1

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
