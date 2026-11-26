"""Tests for FeatherOS Compatibility GUI controller, runners, and feather-ctl (Phase 2)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout

from featheros.compat_gui import CompatController
from featheros.ctl import (
    PROFILES,
    apply_profile,
    collect_system_status,
    get_active_profile,
    main as ctl_main,
)
from featheros.runners import (
    RUNTIME_PRESETS,
    fetch_latest_ge_proton,
    list_installed_runners,
    parse_ge_proton_release,
    safe_extract_tarball,
)
from tests.test_featherrun_core import make_mock_probe, make_synthetic_pe


class TestRunners(unittest.TestCase):
    def test_list_custom_ge_proton_runner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "feather"
            wine_bin = home / "runners" / "GE-Proton9-25" / "files" / "bin" / "wine"
            wine_bin.parent.mkdir(parents=True)
            wine_bin.write_text("#!/bin/sh\n", encoding="utf-8")

            runners = list_installed_runners(home=home)
            names = [r.name for r in runners]
            self.assertEqual(names, ["system-wine", "GE-Proton9-25"])
            self.assertEqual(runners[1].kind, "ge-proton")

    def test_parse_and_fetch_ge_proton_release(self) -> None:
        sample_payload = {
            "tag_name": "GE-Proton9-25",
            "assets": [
                {"name": "GE-Proton9-25.sha512sum", "browser_download_url": "https://example/sha"},
                {
                    "name": "GE-Proton9-25.tar.gz",
                    "browser_download_url": "https://example/GE-Proton9-25.tar.gz",
                    "size": 450000000,
                },
            ],
        }
        asset = parse_ge_proton_release(sample_payload)
        self.assertEqual(asset.tag, "GE-Proton9-25")
        self.assertTrue(asset.asset_name.endswith(".tar.gz"))

        fetched = fetch_latest_ge_proton(fetcher=lambda _u: json.dumps(sample_payload).encode("utf-8"))
        self.assertEqual(fetched.tag, "GE-Proton9-25")

    def test_safe_extract_blocks_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_tar = Path(tmp) / "evil.tar.gz"
            with tarfile.open(bad_tar, "w:gz") as tf:
                info = tarfile.TarInfo(name="../escape.txt")
                data = b"pwn"
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            with self.assertRaises(ValueError):
                safe_extract_tarball(bad_tar, Path(tmp) / "out")


class TestFeatherCtl(unittest.TestCase):
    def test_profile_switching_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            ran: list[list[str]] = []

            self.assertEqual(get_active_profile(cfg_dir).name, "balanced")

            res = apply_profile("low-ram", config_dir=cfg_dir, runner=lambda cmd: (ran.append(cmd) or 0))
            self.assertEqual(res["profile"]["name"], "low-ram")
            self.assertEqual(get_active_profile(cfg_dir).name, "low-ram")
            self.assertIn(["pkill", "-x", "picom"], ran)

            res_bal = apply_profile("balanced", config_dir=cfg_dir, dry_run=True)
            self.assertTrue(res_bal["dry_run"])
            # dry-run does not overwrite persisted profile
            self.assertEqual(get_active_profile(cfg_dir).name, "low-ram")

    def test_ctl_cli_status_and_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = str(Path(tmp) / "home")
            cfg = str(Path(tmp) / "cfg")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ctl_main(["--home", home, "--config-dir", cfg, "status", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["os"], "FeatherOS")
            self.assertIn(payload["active_profile"]["name"], PROFILES)


class TestCompatController(unittest.TestCase):
    def test_controller_bottle_runtime_and_launch_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cfg_dir = Path(tmp) / "cfg"
            probe_no_wine = make_mock_probe(vulkan_hw=False)
            # Simulate preview environment without wine binary
            preview_probe = probe_no_wine.__class__(
                **{**probe_no_wine.to_dict(), "wine_path": None, "wine64_path": None, "winetricks_path": None}
            )
            ctrl = CompatController(home=home, config_dir=cfg_dir, probe=preview_probe)

            # default bottle exists automatically
            self.assertTrue(any(b.slug == "default" for b in ctrl.list_bottles()))
            with self.assertRaises(ValueError):
                ctrl.delete_bottle("default")

            b = ctrl.create_bottle("Steam Games", windows_version="win11", dxvk=True)
            self.assertEqual(b.slug, "steam-games")

            exe = make_synthetic_pe(Path(tmp) / "demo.exe")
            plan, launched, msg = ctrl.launch_binary(exe, "steam-games")
            self.assertFalse(launched)
            self.assertEqual(plan.effective_backend, "wined3d")
            self.assertIn("preview mode", msg)

            ok, rt_msg = ctrl.install_runtime_preset("steam-games", RUNTIME_PRESETS[0].id)
            self.assertFalse(ok)
            self.assertIn("winetricks -q vcrun2022", rt_msg)

            st = collect_system_status(home=home, config_dir=cfg_dir, probe=preview_probe)
            self.assertEqual(st["bottles_count"], 2)


if __name__ == "__main__":
    unittest.main()
