"""Shared Windows 11 Dark Glass (Fluent) GTK3 stylesheet for FeatherOS apps."""

from __future__ import annotations

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

.feather-accent {
    color: #38bdf8;
    font-weight: 700;
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
    border-color: rgba(255, 255, 255, 0.04);
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

checkbutton {
    color: #e2e8f0;
}

separator {
    background-color: rgba(255, 255, 255, 0.08);
}
"""


def apply_fluent_gtk_theme() -> bool:
    """Apply FeatherOS Windows 11 Dark Glass CSS to the active GTK3 screen."""
    try:
        import gi  # type: ignore[import-not-found]

        gi.require_version("Gtk", "3.0")
        from gi.repository import Gdk, Gtk  # type: ignore[import-not-found]
    except (ImportError, ValueError):
        return False

    settings = Gtk.Settings.get_default()
    if settings is not None:
        settings.set_property("gtk-application-prefer-dark-theme", True)

    provider = Gtk.CssProvider()
    provider.load_from_data(FLUENT_DARK_GTK_CSS.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    return True
