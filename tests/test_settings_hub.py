"""Unit tests for FeatherOS Windows-style Unified Settings Hub (v0.2.0)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import xml.etree.ElementTree as ET

from featheros.fluent_theme import escape_pango
from featheros.runners import RUNTIME_PRESETS
from featheros.settings_hub import SECTIONS, SETTINGS_ACTIONS, SettingsController, main as settings_main
from featheros.store import CATALOG


class TestFeatherSettingsHub(unittest.TestCase):
    def test_sections_and_tool_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def fake_which(name: str) -> str | None:
                return f"/usr/bin/{name}" if name in ("xfce4-display-settings", "pavucontrol") else None

            ctrl = SettingsController(home=Path(tmp), config_dir=Path(tmp) / "cfg", which=fake_which)
            self.assertEqual(len(ctrl.list_sections()), len(SECTIONS))

            sys_items = ctrl.list_actions(section="system")
            disp = next(i for i in sys_items if i["id"] == "display")
            pwr = next(i for i in sys_items if i["id"] == "power")
            self.assertTrue(disp["available"])
            self.assertFalse(pwr["available"])

            ok_dry, msg_dry = ctrl.run_action("display", dry_run=True)
            self.assertTrue(ok_dry)
            self.assertIn("xfce4-display-settings", msg_dry)

            ok_missing, msg_missing = ctrl.run_action("power")
            self.assertFalse(ok_missing)
            self.assertIn("preview mode", msg_missing)

    def test_cli_list_and_dry_run_open(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = settings_main(["list", "--section", "personalization", "--json"])
        self.assertEqual(rc, 0)
        items = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(items), 3)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = settings_main(["open", "sound", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("pavucontrol", buf.getvalue())

    def test_all_gtk_pango_markup_strings_are_valid_xml(self) -> None:
        # Regression guard: unescaped '&' (e.g. 'Display & Resolution') broke GTK3 Pango markup!
        for _sid, label in SECTIONS:
            ET.fromstring(f"<m><b><big>{escape_pango(label)}</big></b></m>")
        for act in SETTINGS_ACTIONS:
            ET.fromstring(
                f"<m><b>{escape_pango(act.title)}</b>\n<small>{escape_pango(act.description)}</small></m>"
            )
        for app in CATALOG:
            ET.fromstring(
                f"<m><b>{escape_pango(app.name)}</b> <small>({escape_pango(app.size_hint)})</small>\n"
                f"<small>{escape_pango(app.summary)}</small></m>"
            )
        for preset in RUNTIME_PRESETS:
            ET.fromstring(
                f"<m><b>{escape_pango(preset.label)}</b>\n<small>{escape_pango(preset.description)}</small></m>"
            )


if __name__ == "__main__":
    unittest.main()
