"""Tests for FeatherOS ISO build pipeline, package lists, CI workflow, and scripts (Phase 4)."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestBuildPipeline(unittest.TestCase):
    def test_validate_build_script_passes(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate-build.py")],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"Validator failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("PASSED", proc.stdout)

    def test_iso_builder_contains_hybrid_uefi_and_bios_steps(self) -> None:
        text = (REPO_ROOT / "build" / "build-iso.sh").read_text(encoding="utf-8")
        self.assertIn("debootstrap", text)
        self.assertIn("mksquashfs", text)
        self.assertIn("x86_64-efi", text)
        self.assertIn("i386-pc", text)
        self.assertIn("xorriso", text)
        self.assertIn("trap cleanup EXIT", text)

    def test_chroot_enables_multiarch_and_installs_featheros(self) -> None:
        text = (REPO_ROOT / "build" / "chroot-setup.sh").read_text(encoding="utf-8")
        self.assertIn("dpkg --add-architecture i386", text)
        self.assertIn("/usr/local/bin/feather-run", text)
        self.assertIn("/usr/local/bin/feather-compat", text)
        self.assertIn("/usr/local/bin/feather-ctl", text)
        self.assertIn("plymouth-set-default-theme featheros", text)

    def test_ci_workflow_runs_tests_and_builds_iso(self) -> None:
        wf = (REPO_ROOT / ".github" / "workflows" / "build-iso.yml").read_text(encoding="utf-8")
        self.assertIn("unittest discover", wf)
        self.assertIn("scripts/validate-build.py", wf)
        self.assertIn("build/build-iso.sh", wf)
        self.assertIn("qemu-system-x86_64", wf)
        self.assertIn("featheros-boot-proof", wf)
        self.assertIn("actions/upload-artifact", wf)


if __name__ == "__main__":
    unittest.main()
