"""Tests for FeatherOS Compatibility GUI controller, runners, and feather-ctl."""

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
    apply_theme_mode,
    collect_system_status,
    get_active_profile,
    get_theme_mode,
    main as ctl_main,
)
from featheros.runners import (
    RUNTIME_PRESETS,
    fetch_latest_ge_proton,
    install_ge_proton,
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

    def test_parse_fetch_and_install_ge_proton_release(self) -> None:
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

        # Build a valid synthetic GE-Proton tarball and verify live install_ge_proton()
        with tempfile.TemporaryDirectory() as tmp:
            tar_buf = io.BytesIO()
            with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
                content = b"#!/bin/sh\necho wine\n"
                info = tarfile.TarInfo(name="GE-Proton9-25/files/bin/wine")
                info.size = len(content)
                tf.addfile(info, io.BytesIO(content))
            tar_bytes = tar_buf.getvalue()

            def fake_downloader(_url: str, dest: Path) -> None:
                dest.write_bytes(tar_bytes)

            home = Path(tmp) / "home"
            installed_asset = install_ge_proton(
                home=home,
                fetcher=lambda _u: json.dumps(sample_payload).encode("utf-8"),
                downloader=fake_downloader,
            )
            self.assertEqual(installed_asset.tag, "GE-Proton9-25")
            runners = list_installed_runners(home=home)
            self.assertTrue(any(r.name == "GE-Proton9-25" for r in runners))

    def test_safe_extract_blocks_path_and_symlink_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_tar = Path(tmp) / "evil.tar.gz"
            with tarfile.open(bad_tar, "w:gz") as tf:
                info = tarfile.TarInfo(name="../escape.txt")
                data = b"pwn"
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            with self.assertRaises(ValueError):
                safe_extract_tarball(bad_tar, Path(tmp) / "out")

            # Sibling prefix bypass attempt (../out_evil/pwn.txt)
            sib_tar = Path(tmp) / "sib.tar.gz"
            with tarfile.open(sib_tar, "w:gz") as tf:
                info = tarfile.TarInfo(name="../out_evil/pwn.txt")
                data = b"pwn"
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))

            with self.assertRaises(ValueError):
                safe_extract_tarball(sib_tar, Path(tmp) / "out")

            # Escaping symlink attempt
            sym_tar = Path(tmp) / "sym.tar.gz"
            with tarfile.open(sym_tar, "w:gz") as tf:
                info = tarfile.TarInfo(name="link")
                info.type = tarfile.SYMTYPE
                info.linkname = "../../etc/passwd"
                tf.addfile(info)

            with self.assertRaises(ValueError):
                safe_extract_tarball(sym_tar, Path(tmp) / "out")

            # Escaping hardlink attempt (tar hardlink targets are relative to extraction root)
            lnk_tar = Path(tmp) / "lnk.tar.gz"
            with tarfile.open(lnk_tar, "w:gz") as tf:
                info = tarfile.TarInfo(name="sub/hardlink")
                info.type = tarfile.LNKTYPE
                info.linkname = "../outside.txt"
                tf.addfile(info)

            with self.assertRaises(ValueError):
                safe_extract_tarball(lnk_tar, Path(tmp) / "out")

            # Non-HTTPS GE-Proton download URL rejected
            with self.assertRaises(ValueError):
                parse_ge_proton_release(
                    {
                        "tag_name": "GE-Proton9-25",
                        "assets": [{"name": "GE-Proton9-25.tar.gz", "browser_download_url": "http://evil/x.tar.gz"}],
                    }
                )


class TestFeatherCtl(unittest.TestCase):
    def test_profile_switching_theme_mode_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_dir = Path(tmp) / "cfg"
            ran: list[list[str]] = []

            self.assertEqual(get_active_profile(cfg_dir).name, "balanced")
            self.assertEqual(get_theme_mode(cfg_dir), "dark")

            res = apply_profile("low-ram", config_dir=cfg_dir, runner=lambda cmd: (ran.append(cmd) or 0))
            self.assertEqual(res["profile"]["name"], "low-ram")
            self.assertEqual(get_active_profile(cfg_dir).name, "low-ram")
            self.assertIn(
                ["xfconf-query", "-c", "xfwm4", "-p", "/general/use_compositing", "-s", "false"],
                ran,
            )
            self.assertFalse(any("picom" in cmd for cmd in ran))

            theme_ran: list[list[str]] = []
            tres = apply_theme_mode("light", config_dir=cfg_dir, runner=lambda cmd: (theme_ran.append(cmd) or 0))
            self.assertEqual(tres["mode"], "light")
            self.assertEqual(get_theme_mode(cfg_dir), "light")
            self.assertTrue(any("FeatherWin11-Light" in cmd for cmd in theme_ran))

            res_bal = apply_profile("balanced", config_dir=cfg_dir, dry_run=True)
            self.assertTrue(res_bal["dry_run"])
            # dry-run does not overwrite persisted profile
            self.assertEqual(get_active_profile(cfg_dir).name, "low-ram")

    def test_ctl_cli_status_profile_and_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = str(Path(tmp) / "home")
            cfg = str(Path(tmp) / "cfg")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = ctl_main(["--home", home, "--config-dir", cfg, "status", "--json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(payload["os"], "FeatherOS")
            self.assertEqual(payload["theme_mode"], "dark")
            self.assertIn(payload["active_profile"]["name"], PROFILES)

            buf2 = io.StringIO()
            with redirect_stdout(buf2):
                rc2 = ctl_main(["--home", home, "--config-dir", cfg, "theme", "light", "--dry-run", "--json"])
            self.assertEqual(rc2, 0)
            self.assertEqual(json.loads(buf2.getvalue())["mode"], "light")


class TestCompatController(unittest.TestCase):
    def test_controller_bottle_runtime_and_launch_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            cfg_dir = Path(tmp) / "cfg"
            probe_no_wine = make_mock_probe(vulkan_hw=False)
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
