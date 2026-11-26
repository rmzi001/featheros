"""Validation tests for FeatherShell desktop overlay configs, XML, MIME, and LF endings."""

from __future__ import annotations

import configparser
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parent.parent
OVERLAY_ROOT = REPO_ROOT / "desktop" / "overlay"


class TestFeatherShellOverlay(unittest.TestCase):
    def test_required_overlay_files_exist(self) -> None:
        required = [
            "etc/featheros-release",
            "etc/issue",
            "etc/sysctl.d/99-featheros.conf",
            "etc/security/limits.d/99-featheros-esync.conf",
            "etc/default/zramswap",
            "etc/skel/.config/mimeapps.list",
            "etc/skel/.config/gtk-3.0/settings.ini",
            "etc/skel/.config/Thunar/uca.xml",
            "etc/skel/.config/xfce4/panel/whiskermenu-2.rc",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xsettings.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-desktop.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-keyboard-shortcuts.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-notifyd.xml",
            "etc/skel/.config/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml",
            "etc/xdg/autostart/feather-firstboot.desktop",
            "etc/xdg/autostart/feather-polkit.desktop",
            "etc/xdg/autostart/feather-clipman.desktop",
            "etc/xdg/menus/applications-merged/feather-windows.menu",
            "etc/lightdm/lightdm.conf.d/50-featheros.conf",
            "etc/systemd/system/feather-boot-report.service",
            "etc/calamares/branding/featheros/show.qml",
            "etc/calamares/modules/removeuser.conf",
            "etc/calamares/modules/packages.conf",
            "etc/calamares/modules/shellprocess.conf",
            "usr/share/themes/FeatherWin11-Dark/gtk-3.0/gtk.css",
            "usr/share/themes/FeatherWin11-Dark/xfwm4/themerc",
            "usr/share/themes/FeatherWin11-Light/gtk-3.0/gtk.css",
            "usr/share/themes/FeatherWin11-Light/xfwm4/themerc",
            "usr/share/icons/hicolor/scalable/apps/featheros-start.svg",
            "usr/share/applications/feather-run.desktop",
            "usr/share/applications/feather-compat.desktop",
            "usr/share/applications/feather-store.desktop",
            "usr/share/applications/feather-settings.desktop",
            "usr/share/applications/feather-install.desktop",
            "usr/share/backgrounds/featheros/wallpaper.svg",
            "usr/share/backgrounds/featheros/wallpaper-light.svg",
            "usr/share/plymouth/themes/featheros/featheros.plymouth",
            "usr/local/bin/feather-firstboot",
            "usr/local/bin/feather-polkit-agent",
            "usr/local/bin/feather-calamares",
            "usr/local/bin/feather-boot-report",
        ]
        for rel in required:
            self.assertTrue((OVERLAY_ROOT / rel).is_file(), f"Missing overlay file: {rel}")

    def test_xml_and_svg_files_are_well_formed(self) -> None:
        xml_files = list(OVERLAY_ROOT.rglob("*.xml")) + list(OVERLAY_ROOT.rglob("*.svg"))
        self.assertGreaterEqual(len(xml_files), 3)
        for path in xml_files:
            ET.parse(path)

    def test_desktop_entries_valid_and_mime_associations(self) -> None:
        desktop_files = list(OVERLAY_ROOT.rglob("*.desktop"))
        self.assertGreaterEqual(len(desktop_files), 4)
        for df in desktop_files:
            parser = configparser.ConfigParser(interpolation=None)
            parser.read(df, encoding="utf-8")
            self.assertIn("Desktop Entry", parser, f"Missing [Desktop Entry] in {df}")
            entry = parser["Desktop Entry"]
            self.assertIn("Name", entry)
            self.assertIn("Type", entry)
            if entry["Type"] == "Application":
                self.assertIn("Exec", entry)

        mime = configparser.ConfigParser(interpolation=None)
        mime.read(OVERLAY_ROOT / "etc/skel/.config/mimeapps.list", encoding="utf-8")
        defaults = mime["Default Applications"]
        self.assertEqual(defaults["application/x-ms-dos-executable"], "feather-run.desktop")
        self.assertEqual(defaults["application/x-msi"], "feather-run.desktop")

    def test_linux_files_have_strict_lf_line_endings(self) -> None:
        checked = 0
        for root in (OVERLAY_ROOT, REPO_ROOT / "config"):
            for path in root.rglob("*"):
                if path.is_file():
                    raw = path.read_bytes()
                    self.assertNotIn(
                        b"\r\n",
                        raw,
                        f"CRLF line ending found in Linux file: {path.relative_to(REPO_ROOT)}",
                    )
                    checked += 1
        self.assertGreater(checked, 15)


if __name__ == "__main__":
    unittest.main()
