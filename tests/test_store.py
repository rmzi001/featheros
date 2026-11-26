"""Tests for FeatherStore Welcome & Curated App Hub."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout

from featheros.store import CATALOG, StoreController, main as store_main


class TestFeatherStore(unittest.TestCase):
    def test_catalog_detection_and_apt_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def fake_which(name: str) -> str | None:
                return f"/usr/bin/{name}" if name in ("apt-get", "pkexec", "firefox-esr", "calamares") else None

            ctrl = StoreController(home=Path(tmp), which=fake_which)
            self.assertTrue(ctrl.has_calamares_installer())

            browsers = ctrl.list_apps(category="browsers")
            ff = next(b for b in browsers if b["id"] == "firefox-esr")
            chrom = next(b for b in browsers if b["id"] == "chromium")
            self.assertTrue(ff["installed"])
            self.assertFalse(chrom["installed"])

            plan = ctrl.build_install_plan("steam")
            self.assertTrue(plan.can_execute_locally)
            self.assertEqual(
                plan.command,
                ["/usr/bin/pkexec", "apt-get", "install", "-y", "--no-install-recommends", "steam-installer"],
            )

    def test_preview_mode_without_apt_and_ge_proton_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            wine_bin = home / "runners" / "GE-Proton9-25" / "files" / "bin" / "wine"
            wine_bin.parent.mkdir(parents=True)
            wine_bin.write_text("#!/bin/sh\n", encoding="utf-8")

            ctrl = StoreController(home=home, which=lambda _n: None)
            ge_app = ctrl.get_app("ge-proton")
            self.assertTrue(ctrl.is_installed(ge_app))

            plan = ctrl.build_install_plan("chromium")
            self.assertFalse(plan.can_execute_locally)
            self.assertIn("preview mode", plan.note)

    def test_cli_list_and_dry_run_install(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = store_main(["list", "--category", "gaming", "--json"])
        self.assertEqual(rc, 0)
        items = json.loads(buf.getvalue())
        self.assertGreaterEqual(len(items), 3)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = store_main(["install", "vlc", "--dry-run"])
        self.assertEqual(rc, 0)
        self.assertIn("vlc", buf.getvalue())
        self.assertGreaterEqual(len(CATALOG), 10)


if __name__ == "__main__":
    unittest.main()
