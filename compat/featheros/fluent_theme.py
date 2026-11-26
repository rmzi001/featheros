"""Shared Windows 11 Dark & Light Glass (Fluent) GTK3 stylesheets for FeatherOS apps."""

from __future__ import annotations

import json
import os
from pathlib import Path

FLUENT_DARK_GTK_CSS = """
window, .background {
    background-color: #141821;
    color: #f1f5f9;
}

headerbar, .titlebar {
    background-color: #10141c;
    color: #f8fafc;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

notebook > header {
    background-color: #10141c;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

notebook > header > tabs > tab {
    background-color: transparent;
    color: #94a3b8;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}

notebook > header > tabs > tab:checked {
    color: #38bdf8;
    border-bottom: 2px solid #38bdf8;
    background-color: rgba(56, 189, 248, 0.08);
}

notebook > stack {
    background-color: #141821;
}

list, listbox {
    background-color: #10141c;
    color: #e2e8f0;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 10px;
}

list row, listbox row {
    padding: 8px 12px;
    border-radius: 8px;
    margin: 2px 4px;
    color: #cbd5e1;
}

list row:selected, listbox row:selected {
    background-color: rgba(56, 189, 248, 0.18);
    color: #ffffff;
    border-left: 3px solid #38bdf8;
}

.feather-card {
    background-color: #1c2230;
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 12px 14px;
}

.feather-title {
    color: #f8fafc;
    font-weight: 700;
    font-size: 16px;
}

.feather-subtitle {
    color: #94a3b8;
    font-size: 12px;
}

.feather-badge-ok {
    background-color: rgba(16, 185, 129, 0.16);
    color: #34d399;
    border: 1px solid rgba(52, 211, 153, 0.45);
    border-radius: 999px;
    padding: 4px 12px;
    font-weight: 600;
}

button {
    background-image: none;
    background-color: #242c3d;
    color: #f1f5f9;
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 8px;
    padding: 6px 14px;
    box-shadow: none;
}

button:hover {
    background-color: #2e3950;
    border-color: rgba(56, 189, 248, 0.55);
}

button.suggested-action, button.feather-primary {
    background-color: #0284c7;
    color: #ffffff;
    border-color: #38bdf8;
}

button.suggested-action:hover, button.feather-primary:hover {
    background-color: #0ea5e9;
}

button:disabled {
    background-color: #1a202c;
    color: #64748b;
    border-color: rgba(255, 255, 255, 0.05);
}

entry, combobox button {
    background-color: #1c2230;
    color: #f8fafc;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    padding: 6px 10px;
}

entry:focus {
    border-color: #38bdf8;
}
"""

FLUENT_LIGHT_GTK_CSS = """
window, .background {
    background-color: #f3f6fb;
    color: #0f172a;
}

headerbar, .titlebar {
    background-color: #e8eef7;
    color: #0f172a;
    border-bottom: 1px solid rgba(15, 23, 42, 0.10);
}

notebook > header {
    background-color: #e8eef7;
    border-bottom: 1px solid rgba(15, 23, 42, 0.10);
}

notebook > header > tabs > tab {
    background-color: transparent;
    color: #475569;
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}

notebook > header > tabs > tab:checked {
    color: #0284c7;
    border-bottom: 2px solid #0284c7;
    background-color: rgba(2, 132, 199, 0.08);
}

notebook > stack {
    background-color: #f3f6fb;
}

list, listbox {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid rgba(15, 23, 42, 0.10);
    border-radius: 10px;
}

list row:selected, listbox row:selected {
    background-color: rgba(2, 132, 199, 0.14);
    color: #0369a1;
    border-left: 3px solid #0284c7;
}

.feather-card {
    background-color: #ffffff;
    border: 1px solid rgba(15, 23, 42, 0.09);
    border-radius: 10px;
    padding: 12px 14px;
}

.feather-title {
    color: #0f172a;
    font-weight: 700;
    font-size: 16px;
}

.feather-subtitle {
    color: #475569;
    font-size: 12px;
}

.feather-badge-ok {
    background-color: rgba(16, 185, 129, 0.14);
    color: #047857;
    border: 1px solid rgba(4, 120, 87, 0.35);
    border-radius: 999px;
    padding: 4px 12px;
    font-weight: 600;
}

button {
    background-image: none;
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid rgba(15, 23, 42, 0.14);
    border-radius: 8px;
    padding: 6px 14px;
    box-shadow: none;
}

button:hover {
    background-color: #e2e8f0;
    border-color: #0284c7;
}

button.suggested-action, button.feather-primary {
    background-color: #0284c7;
    color: #ffffff;
    border-color: #0284c7;
}

entry, combobox button {
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid rgba(15, 23, 42, 0.16);
    border-radius: 8px;
    padding: 6px 10px;
}
"""


def read_theme_mode(config_dir: str | Path | None = None) -> str:
    """Return persisted FeatherOS theme mode ('dark' or 'light')."""
    if config_dir is not None:
        base = Path(config_dir)
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        base = (Path(xdg) / "featheros") if xdg else (Path.home() / ".config" / "featheros")
    cfg = base / "theme.json"
    if cfg.is_file():
        try:
            mode = str(json.loads(cfg.read_text(encoding="utf-8")).get("mode", "dark")).lower()
            if mode in ("dark", "light"):
                return mode
        except (OSError, ValueError):
            pass
    return "dark"


def apply_fluent_gtk_theme(mode: str | None = None) -> bool:
    """Apply FeatherOS Windows 11 Dark or Light Glass CSS to the active GTK3 screen."""
    try:
        import gi  # type: ignore[import-not-found]

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk, Gtk  # type: ignore[import-not-found]
    except (ImportError, ValueError):
        return False

    resolved = mode if mode in ("dark", "light") else read_theme_mode()
    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", resolved == "dark")

    css = FLUENT_LIGHT_GTK_CSS if resolved == "light" else FLUENT_DARK_GTK_CSS
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    return True
