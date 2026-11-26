"""Tests for FeatherOS Automated In-OS QA Checking Agent (feather-selftest)."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from featheros.selftest import ESSENTIAL_BINARIES, run_selftest
from tests.test_featherrun_core import make_mock_probe


class TestFeatherSelftest(unittest.TestCase):
    def test_perfect_100_score_on_healthy_featheros(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc").mkdir(parents=True)
            (root / "etc" / "os-release").write_text('PRETTY_NAME="FeatherOS 0.3.0"\n', encoding="utf-8")
            (root / "etc" / "issue").write_text("FeatherOS 0.3.0\n", encoding="utf-8")
            (root / "boot").mkdir()
            (root / "boot" / "vmlinuz-6.12.0-amd64").write_bytes(b"vmlinuz")

            for rel in (
                "usr/share/themes/FeatherWin11-Dark/gtk-3.0/gtk.css",
                "usr/share/themes/FeatherWin11-Light/gtk-3.0/gtk.css",
                "usr/share/themes/FeatherWin11-Dark/xfwm4/themerc",
                "etc/xdg/autostart/feather-polkit.desktop",
                "usr/lib/x86_64-linux-gnu/polkit-mate-authentication-agent-1",
                "etc/calamares/branding/featheros/show.qml",
                "etc/calamares/modules/removeuser.conf",
            ):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("ok\n", encoding="utf-8")

            def fake_which(name: str) -> str | None:
                if name in ESSENTIAL_BINARIES or name in ("systemctl", "swapon"):
                    return f"/usr/bin/{name}"
                return None

            def fake_run(cmd: list[str], _timeout: int) -> tuple[int, str]:
                if "systemctl" in cmd[0]:
                    return 0, ""
                if "swapon" in cmd[0]:
                    return 0, "/dev/zram0 partition 1G 0B 100"
                if "echo FEATHEROS_WIN32_OK" in cmd:
                    return 0, "FEATHEROS_WIN32_OK"
                return 0, ""

            probe = make_mock_probe(vulkan_hw=True)
            low_ram_probe = probe.__class__(
                **{**probe.to_dict(), "ram_total_mb": 2048, "ram_available_mb": 1650}
            )
            report = run_selftest(
                run_cmd=fake_run,
                which=fake_which,
                root=root,
                probe=low_ram_probe,
                run_wine_smoke=True,
            )
            self.assertEqual(report["score"], 100, report)
            self.assertEqual(report["passed_count"], report["total_checks"])

    def test_detects_missing_kernel_and_legacy_debt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "etc" / "xdg" / "openbox").mkdir(parents=True)
            (root / "etc" / "xdg" / "openbox" / "rc.xml").write_text("<openbox_config/>", encoding="utf-8")

            report = run_selftest(
                run_cmd=lambda _c, _t: (1, "failed"),
                which=lambda _n: None,
                root=root,
                probe=make_mock_probe(vulkan_hw=False),
                run_wine_smoke=False,
            )
            checks = {c["id"]: c for c in report["checks"]}
            self.assertFalse(checks["calamares_ready"]["passed"])
            self.assertFalse(checks["no_legacy_debt"]["passed"])
            self.assertLess(report["score"], 50)


if __name__ == "__main__":
    unittest.main()
