"""feather-compat: Lightweight Compatibility Manager GUI for FeatherOS (v0.3.0)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
from typing import Any, Sequence

from . import __version__
from .bottles import (
    BottleConfig,
    BottleManager,
    LaunchPlan,
    VALID_WINDOWS_VERSIONS,
)
from .ctl import PROFILES, apply_profile, collect_system_status, get_active_profile
from .fluent_theme import apply_fluent_gtk_theme, escape_pango
from .runners import RUNTIME_PRESETS, InstalledRunner, list_installed_runners
from .shortcuts import WindowsShortcut, discover_bottle_shortcuts, prune_bottle_shortcuts, sync_bottle_shortcuts
from .system_probe import SystemProbe, probe_system


class CompatController:
    """UI-agnostic controller powering both GTK3 and Tkinter frontends."""

    def __init__(
        self,
        *,
        home: str | Path | None = None,
        config_dir: str | Path | None = None,
        probe: SystemProbe | None = None,
    ) -> None:
        self.home = home
        self.config_dir = config_dir
        self.manager = BottleManager(home=home)
        self.probe = probe or probe_system()
        self.manager.ensure_bottle("default")

    def list_bottles(self) -> list[BottleConfig]:
        return self.manager.list_bottles()

    def get_bottle(self, slug: str) -> BottleConfig:
        return self.manager.get_bottle(slug)

    def create_bottle(
        self,
        name: str,
        *,
        windows_version: str = "win10",
        dxvk: bool = True,
        vkd3d: bool = True,
        virtual_desktop: str | None = None,
    ) -> BottleConfig:
        return self.manager.create_bottle(
            name,
            windows_version=windows_version,
            dxvk=dxvk,
            vkd3d=vkd3d,
            virtual_desktop=virtual_desktop or None,
        )

    def update_bottle(self, slug: str, **kwargs: Any) -> BottleConfig:
        cfg = self.manager.update_bottle(slug, **kwargs)
        if self.probe.can_run_wine:
            threading.Thread(
                target=self.manager.apply_bottle_settings,
                args=(cfg.slug,),
                kwargs={"probe": self.probe},
                daemon=True,
            ).start()
        return cfg

    def delete_bottle(self, slug: str) -> bool:
        if slug == "default":
            raise ValueError("Cannot delete the built-in 'default' bottle")
        deleted = self.manager.delete_bottle(slug)
        prune_bottle_shortcuts(slug)
        return deleted

    def list_apps(self, slug: str) -> list[WindowsShortcut]:
        return discover_bottle_shortcuts(self.manager, slug)

    def sync_shortcuts(self, slug: str) -> list[Path]:
        return sync_bottle_shortcuts(self.manager, slug)

    def plan_launch(self, target: str | Path, bottle_slug: str) -> LaunchPlan:
        return self.manager.build_launch_plan(target, bottle_name=bottle_slug, probe=self.probe)

    def launch_binary(self, target: str | Path, bottle_slug: str) -> tuple[LaunchPlan, bool, str]:
        """Build a launch plan, apply prefix settings if needed, launch, and sync shortcuts."""
        plan = self.plan_launch(target, bottle_slug)
        if not plan.binary_info.valid:
            return plan, False, f"Invalid binary: {plan.binary_info.error}"
        if not self.probe.can_run_wine:
            return (
                plan,
                False,
                "Wine is not installed on this host (preview mode). "
                f"Resolved command: {' '.join(plan.command)}",
            )
        self.manager.touch_last_used(plan.bottle.slug)
        merged = os.environ.copy()
        merged.update(plan.env)

        def _spawn_and_sync() -> None:
            if not (plan.prefix_path / "system.reg").is_file():
                self.manager.apply_bottle_settings(plan.bottle.slug, probe=self.probe)
            proc = subprocess.Popen(plan.command, env=merged)
            proc.wait()
            sync_bottle_shortcuts(self.manager, plan.bottle.slug)

        threading.Thread(target=_spawn_and_sync, daemon=True).start()
        note = f" ({'; '.join(plan.notices)})" if plan.notices else ""
        return plan, True, f"Launched {Path(target).name} [{plan.effective_backend}]{note}"

    def install_runtime_preset(self, bottle_slug: str, preset_id: str) -> tuple[bool, str]:
        preset = next((p for p in RUNTIME_PRESETS if p.id == preset_id), None)
        if preset is None:
            return False, f"Unknown runtime preset: {preset_id}"
        cmd, env = self.manager.build_winetricks_command(bottle_slug, list(preset.verbs))
        if not self.probe.winetricks_path:
            return False, f"winetricks not installed on this host. Would run: {' '.join(cmd)}"
        merged = os.environ.copy()
        merged.update(env)
        term = shutil.which("xfce4-terminal")
        if term:
            cmd_str = " ".join(shlex.quote(c) for c in cmd)
            shell_cmd = f"{cmd_str}; echo; read -r -p 'Runtime install complete. Press Enter...' _"
            subprocess.Popen([term, "-x", "bash", "-c", shell_cmd], env=merged)
        else:
            subprocess.Popen(cmd, env=merged)
        return True, f"Installing {preset.label} into bottle '{bottle_slug}'..."

    def list_runners(self) -> list[InstalledRunner]:
        return list_installed_runners(home=self.home)

    def get_system_status(self) -> dict[str, Any]:
        return collect_system_status(home=self.home, config_dir=self.config_dir, probe=self.probe)

    def set_profile(self, profile_name: str) -> dict[str, Any]:
        return apply_profile(profile_name, config_dir=self.config_dir)


def _run_gtk_gui(controller: CompatController) -> int:
    import gi  # type: ignore[import-not-found]

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk  # type: ignore[import-not-found]

    apply_fluent_gtk_theme()

    class FeatherCompatWindow(Gtk.Window):
        def __init__(self) -> None:
            super().__init__(title=f"FeatherOS Compatibility Manager v{__version__}")
            self.set_default_size(900, 600)
            self.set_position(Gtk.WindowPosition.CENTER)
            self.set_icon_name("application-x-ms-dos-executable")
            self.set_border_width(14)

            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.add(root)

            header = Gtk.Label(xalign=0)
            header.get_style_context().add_class("feather-title")
            header.set_markup(
                f"<b><big>FeatherOS Compatibility Manager</big></b>  <small>v{__version__} — "
                f"Graphics: {controller.probe.recommended_graphics_backend.upper()}</small>"
            )
            root.pack_start(header, False, False, 0)

            notebook = Gtk.Notebook()
            root.pack_start(notebook, True, True, 0)

            self.status_bar = Gtk.Label(label="Ready.", xalign=0)
            self.status_bar.get_style_context().add_class("feather-subtitle")
            root.pack_start(self.status_bar, False, False, 0)

            # Tab 1: Bottles & Apps
            tab_bottles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            tab_bottles.set_border_width(10)
            notebook.append_page(tab_bottles, Gtk.Label(label="Bottles & Apps"))

            left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            left_col.set_size_request(230, -1)
            tab_bottles.pack_start(left_col, False, False, 0)

            self.bottle_list = Gtk.ListBox()
            self.bottle_list.connect("row-selected", self._on_bottle_selected)
            left_col.pack_start(self.bottle_list, True, True, 0)

            new_box = Gtk.Box(spacing=6)
            self.new_entry = Gtk.Entry()
            self.new_entry.set_placeholder_text("New bottle name...")
            btn_add = Gtk.Button(label="Add")
            btn_add.get_style_context().add_class("feather-primary")
            btn_add.connect("clicked", self._on_add_bottle)
            new_box.pack_start(self.new_entry, True, True, 0)
            new_box.pack_start(btn_add, False, False, 0)
            left_col.pack_start(new_box, False, False, 0)

            right_scroll = Gtk.ScrolledWindow()
            right_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            tab_bottles.pack_start(right_scroll, True, True, 0)

            right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            right_scroll.add(right_col)

            self.lbl_bottle_title = Gtk.Label(xalign=0)
            right_col.pack_start(self.lbl_bottle_title, False, False, 0)

            btn_row = Gtk.Box(spacing=8)
            btn_run = Gtk.Button(label="Run / Install .exe or .msi...")
            btn_run.get_style_context().add_class("feather-primary")
            btn_run.connect("clicked", self._on_pick_and_run)
            btn_sync = Gtk.Button(label="Sync Start Menu")
            btn_sync.connect("clicked", self._on_sync_shortcuts)
            btn_del = Gtk.Button(label="Delete Bottle")
            btn_del.connect("clicked", self._on_delete_bottle)
            btn_row.pack_start(btn_run, False, False, 0)
            btn_row.pack_start(btn_sync, False, False, 0)
            btn_row.pack_end(btn_del, False, False, 0)
            right_col.pack_start(btn_row, False, False, 0)

            settings_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            settings_card.get_style_context().add_class("feather-card")
            right_col.pack_start(settings_card, False, False, 0)

            grid = Gtk.Grid(column_spacing=12, row_spacing=8)
            settings_card.pack_start(grid, False, False, 0)

            grid.attach(Gtk.Label(label="Windows Version:", xalign=0), 0, 0, 1, 1)
            self.cmb_winver = Gtk.ComboBoxText()
            for ver in VALID_WINDOWS_VERSIONS:
                self.cmb_winver.append(ver, ver.upper())
            grid.attach(self.cmb_winver, 1, 0, 1, 1)

            self.chk_dxvk = Gtk.CheckButton(label="Enable DXVK (DirectX 9/10/11 -> Vulkan)")
            self.chk_vkd3d = Gtk.CheckButton(label="Enable VKD3D-Proton (DirectX 12 -> Vulkan)")
            self.chk_gamemode = Gtk.CheckButton(label="Enable Feral GameMode")
            self.chk_mangohud = Gtk.CheckButton(label="Enable MangoHud FPS Overlay")
            grid.attach(self.chk_dxvk, 0, 1, 2, 1)
            grid.attach(self.chk_vkd3d, 0, 2, 2, 1)
            grid.attach(self.chk_gamemode, 0, 3, 2, 1)
            grid.attach(self.chk_mangohud, 0, 4, 2, 1)

            grid.attach(Gtk.Label(label="Virtual Desktop (e.g. 1280x720):", xalign=0), 0, 5, 1, 1)
            self.ent_vdesktop = Gtk.Entry()
            self.ent_vdesktop.set_placeholder_text("Leave blank for native window")
            grid.attach(self.ent_vdesktop, 1, 5, 1, 1)

            btn_save = Gtk.Button(label="Save & Apply to Prefix")
            btn_save.get_style_context().add_class("feather-primary")
            btn_save.connect("clicked", self._on_save_settings)
            grid.attach(btn_save, 0, 6, 2, 1)

            self.apps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            right_col.pack_start(self.apps_box, False, False, 0)

            # Tab 2: Runtimes
            rt_scroll = Gtk.ScrolledWindow()
            rt_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            tab_rt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            tab_rt.set_border_width(10)
            rt_scroll.add(tab_rt)
            notebook.append_page(rt_scroll, Gtk.Label(label="Windows Runtimes"))
            for preset in RUNTIME_PRESETS:
                row = Gtk.Box(spacing=10)
                row.get_style_context().add_class("feather-card")
                lbl = Gtk.Label(xalign=0)
                lbl.set_markup(
                    f"<b>{escape_pango(preset.label)}</b>\n<small>{escape_pango(preset.description)}</small>"
                )
                btn = Gtk.Button(label="Install")
                btn.get_style_context().add_class("feather-primary")
                btn.connect("clicked", self._on_install_runtime, preset.id)
                row.pack_start(lbl, True, True, 0)
                row.pack_end(btn, False, False, 0)
                tab_rt.pack_start(row, False, False, 0)

            # Tab 3: Performance & Diagnostics
            tab_sys = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            tab_sys.set_border_width(10)
            notebook.append_page(tab_sys, Gtk.Label(label="Performance & System"))
            prof_box = Gtk.Box(spacing=8)
            for key, prof in PROFILES.items():
                btn = Gtk.Button(label=f"Switch: {prof.label}")
                btn.connect("clicked", self._on_switch_profile, key)
                prof_box.pack_start(btn, False, False, 0)
            tab_sys.pack_start(prof_box, False, False, 0)

            diag_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            diag_card.get_style_context().add_class("feather-card")
            self.lbl_diag = Gtk.Label(xalign=0)
            diag_card.pack_start(self.lbl_diag, False, False, 0)
            tab_sys.pack_start(diag_card, False, False, 0)

            self.selected_slug = "default"
            self._refresh_bottles()
            self._refresh_diag()

        def _refresh_bottles(self) -> None:
            for child in self.bottle_list.get_children():
                self.bottle_list.remove(child)
            for bottle in controller.list_bottles():
                row = Gtk.ListBoxRow()
                row.slug = bottle.slug  # type: ignore[attr-defined]
                lbl = Gtk.Label(label=f"{bottle.name} ({bottle.windows_version})", xalign=0)
                lbl.set_margin_start(6)
                row.add(lbl)
                self.bottle_list.add(row)
            self.bottle_list.show_all()
            self._load_bottle(self.selected_slug)

        def _load_bottle(self, slug: str) -> None:
            try:
                b = controller.get_bottle(slug)
            except KeyError:
                b = controller.get_bottle("default")
            self.selected_slug = b.slug
            apps = controller.list_apps(b.slug)
            self.lbl_bottle_title.set_markup(
                f"<b>Bottle: {escape_pango(b.name)}</b>  <small>[{escape_pango(b.arch)}] — {len(apps)} discovered apps</small>"
            )
            self.cmb_winver.set_active_id(b.windows_version)
            self.chk_dxvk.set_active(b.dxvk)
            self.chk_vkd3d.set_active(b.vkd3d)
            self.chk_gamemode.set_active(b.gamemode)
            self.chk_mangohud.set_active(b.mangohud)
            self.ent_vdesktop.set_text(b.virtual_desktop or "")

            for child in self.apps_box.get_children():
                self.apps_box.remove(child)
            if apps:
                hdr = Gtk.Label(xalign=0)
                hdr.set_markup("<b>Installed Windows Apps</b>")
                self.apps_box.pack_start(hdr, False, False, 0)
                for sc in apps:
                    row = Gtk.Box(spacing=10)
                    row.get_style_context().add_class("feather-card")
                    lbl = Gtk.Label(label=sc.name, xalign=0)
                    btn = Gtk.Button(label="Launch")
                    btn.connect("clicked", self._on_launch_discovered, str(sc.target_path))
                    row.pack_start(lbl, True, True, 0)
                    row.pack_end(btn, False, False, 0)
                    self.apps_box.pack_start(row, False, False, 0)
            self.apps_box.show_all()

        def _refresh_diag(self) -> None:
            st = controller.get_system_status()
            s = st["system"]
            p = st["active_profile"]
            self.lbl_diag.set_markup(
                f"<b>Active Profile:</b> {escape_pango(p['label'])} — {escape_pango(p['description'])}\n"
                f"<b>Vulkan Hardware:</b> {escape_pango(s['vulkan_hardware_ready'])} ({escape_pango(s['vulkan_device_name'] or 'none')})\n"
                f"<b>32-bit Multiarch:</b> {escape_pango(s['multiarch_i386'])}\n"
                f"<b>Installed Runners:</b> {escape_pango(', '.join(r['name'] for r in st['runners']))}"
            )

        def _on_launch_discovered(self, _btn: Any, target: str) -> None:
            _plan, _ok, msg = controller.launch_binary(target, self.selected_slug)
            self.status_bar.set_text(msg)

        def _on_bottle_selected(self, _box: Any, row: Any) -> None:
            if row is not None and hasattr(row, "slug"):
                self._load_bottle(row.slug)

        def _on_add_bottle(self, _btn: Any) -> None:
            name = self.new_entry.get_text().strip()
            if not name:
                return
            try:
                cfg = controller.create_bottle(name)
                self.selected_slug = cfg.slug
                self.new_entry.set_text("")
                self._refresh_bottles()
                self.status_bar.set_text(f"Created bottle '{cfg.slug}'.")
            except Exception as exc:
                self.status_bar.set_text(f"Error: {exc}")

        def _on_save_settings(self, _btn: Any) -> None:
            try:
                vd = self.ent_vdesktop.get_text().strip() or None
                controller.update_bottle(
                    self.selected_slug,
                    windows_version=self.cmb_winver.get_active_id() or "win10",
                    dxvk=self.chk_dxvk.get_active(),
                    vkd3d=self.chk_vkd3d.get_active(),
                    gamemode=self.chk_gamemode.get_active(),
                    mangohud=self.chk_mangohud.get_active(),
                    virtual_desktop=vd,
                )
                self._refresh_bottles()
                self.status_bar.set_text(f"Saved & applied settings for '{self.selected_slug}'.")
            except Exception as exc:
                self.status_bar.set_text(f"Error: {exc}")

        def _on_pick_and_run(self, _btn: Any) -> None:
            dialog = Gtk.FileChooserDialog(
                title="Select Windows .exe or .msi",
                parent=self,
                action=Gtk.FileChooserAction.OPEN,
            )
            dialog.add_buttons(
                Gtk.STOCK_CANCEL,
                Gtk.ResponseType.CANCEL,
                Gtk.STOCK_OPEN,
                Gtk.ResponseType.OK,
            )
            flt = Gtk.FileFilter()
            flt.set_name("Windows Programs (*.exe, *.msi)")
            flt.add_pattern("*.exe")
            flt.add_pattern("*.EXE")
            flt.add_pattern("*.msi")
            flt.add_pattern("*.MSI")
            dialog.add_filter(flt)
            if dialog.run() == Gtk.ResponseType.OK:
                path = dialog.get_filename()
                _plan, _ok, msg = controller.launch_binary(path, self.selected_slug)
                self.status_bar.set_text(msg)
            dialog.destroy()

        def _on_sync_shortcuts(self, _btn: Any) -> None:
            written = controller.sync_shortcuts(self.selected_slug)
            self._load_bottle(self.selected_slug)
            self.status_bar.set_text(f"Synced {len(written)} Start Menu shortcuts.")

        def _on_delete_bottle(self, _btn: Any) -> None:
            try:
                controller.delete_bottle(self.selected_slug)
                self.selected_slug = "default"
                self._refresh_bottles()
                self.status_bar.set_text("Deleted bottle.")
            except Exception as exc:
                self.status_bar.set_text(f"Error: {exc}")

        def _on_install_runtime(self, _btn: Any, preset_id: str) -> None:
            _ok, msg = controller.install_runtime_preset(self.selected_slug, preset_id)
            self.status_bar.set_text(msg)

        def _on_switch_profile(self, _btn: Any, key: str) -> None:
            controller.set_profile(key)
            self._refresh_diag()
            self.status_bar.set_text(f"Switched FeatherOS profile to {key}.")

    win = FeatherCompatWindow()
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def _run_tk_gui(controller: CompatController) -> int:
    import tkinter as tk
    from tkinter import filedialog, ttk

    bg = "#141821"
    panel = "#1c2230"
    fg = "#f8fafc"
    muted = "#94a3b8"
    accent = "#38bdf8"

    root = tk.Tk()
    root.title(f"FeatherOS Compatibility Manager v{__version__}")
    root.geometry("860x540")
    root.configure(bg=bg)

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TFrame", background=bg)
    style.configure("Panel.TFrame", background=panel)
    style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("Muted.TLabel", background=bg, foreground=muted, font=("Segoe UI", 9))
    style.configure("Title.TLabel", background=bg, foreground=accent, font=("Segoe UI", 13, "bold"))
    style.configure("TButton", background="#242c3d", foreground=fg, padding=6, borderwidth=1)
    style.map("TButton", background=[("active", "#2e3950"), ("pressed", "#0284c7")])
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.map("TCheckbutton", background=[("active", bg)], foreground=[("active", accent)])
    style.configure("TCombobox", fieldbackground=panel, background=panel, foreground=fg)
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", panel)],
        foreground=[("readonly", fg)],
        selectbackground=[("readonly", panel)],
        selectforeground=[("readonly", fg)],
    )
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=panel, foreground=muted, padding=(14, 7))
    style.map(
        "TNotebook.Tab",
        background=[("selected", "#0284c7"), ("active", "#2e3950")],
        foreground=[("selected", "#ffffff"), ("active", "#f8fafc")],
    )

    header = ttk.Frame(root, padding=12)
    header.pack(fill="x")
    ttk.Label(header, text="FeatherOS Compatibility Manager", style="Title.TLabel").pack(side="left")
    ttk.Label(
        header,
        text=f"v{__version__}  |  Graphics: {controller.probe.recommended_graphics_backend.upper()}",
        style="Muted.TLabel",
    ).pack(side="right")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=12, pady=4)

    status_var = tk.StringVar(value="Ready.")
    ttk.Label(root, textvariable=status_var, style="Muted.TLabel", padding=(12, 6)).pack(fill="x")

    tab_bottles = ttk.Frame(notebook, padding=10)
    notebook.add(tab_bottles, text="Bottles & Apps")

    left = ttk.Frame(tab_bottles)
    left.pack(side="left", fill="y", padx=(0, 12))

    listbox = tk.Listbox(left, width=26, bg=panel, fg=fg, selectbackground=accent, selectforeground="#0f172a", borderwidth=0)
    listbox.pack(fill="y", expand=True)

    new_name_var = tk.StringVar()
    add_bar = ttk.Frame(left, padding=(0, 8, 0, 0))
    add_bar.pack(fill="x")
    tk.Entry(add_bar, textvariable=new_name_var, bg=panel, fg=fg, insertbackground=fg).pack(side="left", fill="x", expand=True)

    right = ttk.Frame(tab_bottles)
    right.pack(side="left", fill="both", expand=True)

    selected_slug = tk.StringVar(value="default")
    winver_var = tk.StringVar(value="win10")
    dxvk_var = tk.BooleanVar(value=True)
    vkd3d_var = tk.BooleanVar(value=True)
    gamemode_var = tk.BooleanVar(value=False)
    vdesk_var = tk.StringVar(value="")

    bottle_title_var = tk.StringVar(value="Bottle: default")
    ttk.Label(right, textvariable=bottle_title_var, font=("Segoe UI", 11, "bold")).pack(anchor="w")

    def refresh_list() -> None:
        listbox.delete(0, tk.END)
        for b in controller.list_bottles():
            listbox.insert(tk.END, b.slug)

    def load_selected(_evt: Any = None) -> None:
        sel = listbox.curselection()
        slug = listbox.get(sel[0]) if sel else selected_slug.get()
        try:
            b = controller.get_bottle(slug)
        except KeyError:
            b = controller.get_bottle("default")
        selected_slug.set(b.slug)
        apps = controller.list_apps(b.slug)
        bottle_title_var.set(f"Bottle: {b.name} [{b.arch}] — {len(apps)} discovered apps")
        winver_var.set(b.windows_version)
        dxvk_var.set(b.dxvk)
        vkd3d_var.set(b.vkd3d)
        gamemode_var.set(b.gamemode)
        vdesk_var.set(b.virtual_desktop or "")

    def add_bottle() -> None:
        name = new_name_var.get().strip()
        if not name:
            return
        try:
            b = controller.create_bottle(name)
            new_name_var.set("")
            selected_slug.set(b.slug)
            refresh_list()
            load_selected()
            status_var.set(f"Created bottle '{b.slug}'.")
        except Exception as exc:
            status_var.set(f"Error: {exc}")

    def save_settings() -> None:
        try:
            controller.update_bottle(
                selected_slug.get(),
                windows_version=winver_var.get(),
                dxvk=dxvk_var.get(),
                vkd3d=vkd3d_var.get(),
                gamemode=gamemode_var.get(),
                virtual_desktop=vdesk_var.get().strip() or None,
            )
            status_var.set(f"Saved settings for '{selected_slug.get()}'.")
        except Exception as exc:
            status_var.set(f"Error: {exc}")

    def pick_and_run() -> None:
        path = filedialog.askopenfilename(
            title="Select Windows .exe or .msi",
            filetypes=[("Windows Apps", "*.exe *.msi"), ("All files", "*.*")],
        )
        if path:
            _plan, _ok, msg = controller.launch_binary(path, selected_slug.get())
            status_var.set(msg)

    ttk.Button(add_bar, text="Add", command=add_bottle).pack(side="left", padx=(6, 0))
    listbox.bind("<<ListboxSelect>>", load_selected)

    actions = ttk.Frame(right, padding=(0, 8))
    actions.pack(fill="x")
    ttk.Button(actions, text="Run / Install .exe or .msi...", command=pick_and_run).pack(side="left")
    ttk.Button(
        actions,
        text="Sync Start Menu",
        command=lambda: status_var.set(
            f"Synced {len(controller.sync_shortcuts(selected_slug.get()))} shortcuts."
        ),
    ).pack(side="left", padx=8)

    form = ttk.Frame(right, padding=(0, 6))
    form.pack(fill="x")
    ttk.Label(form, text="Windows Version:").grid(row=0, column=0, sticky="w", pady=4)
    ttk.Combobox(form, textvariable=winver_var, values=VALID_WINDOWS_VERSIONS, state="readonly").grid(row=0, column=1, sticky="w", padx=8)
    ttk.Checkbutton(form, text="Enable DXVK (DirectX 9/10/11 -> Vulkan)", variable=dxvk_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
    ttk.Checkbutton(form, text="Enable VKD3D-Proton (DirectX 12 -> Vulkan)", variable=vkd3d_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=3)
    ttk.Checkbutton(form, text="Enable GameMode", variable=gamemode_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=3)
    ttk.Label(form, text="Virtual Desktop (e.g. 1280x720):").grid(row=4, column=0, sticky="w", pady=4)
    tk.Entry(form, textvariable=vdesk_var, bg=panel, fg=fg, insertbackground=fg).grid(row=4, column=1, sticky="w", padx=8)
    ttk.Button(form, text="Save Bottle Settings", command=save_settings).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)

    tab_rt = ttk.Frame(notebook, padding=10)
    notebook.add(tab_rt, text="Windows Runtimes")
    for preset in RUNTIME_PRESETS:
        row = ttk.Frame(tab_rt, padding=(0, 4))
        row.pack(fill="x")
        ttk.Label(row, text=f"{preset.label} — {preset.description}").pack(side="left")
        ttk.Button(
            row,
            text="Install",
            command=lambda pid=preset.id: status_var.set(
                controller.install_runtime_preset(selected_slug.get(), pid)[1]
            ),
        ).pack(side="right")

    tab_sys = ttk.Frame(notebook, padding=10)
    notebook.add(tab_sys, text="Performance & System")
    prof_var = tk.StringVar(value=f"Active profile: {get_active_profile(controller.config_dir).label}")
    ttk.Label(tab_sys, textvariable=prof_var, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
    p_bar = ttk.Frame(tab_sys)
    p_bar.pack(fill="x")
    for key, prof in PROFILES.items():
        ttk.Button(
            p_bar,
            text=prof.label,
            command=lambda k=key, lbl=prof.label: (
                controller.set_profile(k),
                prof_var.set(f"Active profile: {lbl}"),
                status_var.set(f"Switched profile to {k}."),
            ),
        ).pack(side="left", padx=(0, 8))

    refresh_list()
    load_selected()
    root.mainloop()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="feather-compat",
        description="FeatherOS Compatibility Manager GUI",
    )
    parser.add_argument("--home", help="Override FEATHEROS_HOME data directory")
    parser.add_argument("--config-dir", help="Override FeatherOS config directory")
    parser.add_argument(
        "--toolkit",
        choices=("auto", "gtk", "tk"),
        default="auto",
        help="Force UI toolkit backend",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    controller = CompatController(home=args.home, config_dir=args.config_dir)

    if args.toolkit in ("auto", "gtk"):
        try:
            return _run_gtk_gui(controller)
        except ImportError:
            if args.toolkit == "gtk":
                print("Error: PyGObject (GTK3) is not installed.", file=sys.stderr)
                return 1

    return _run_tk_gui(controller)


if __name__ == "__main__":
    raise SystemExit(main())
