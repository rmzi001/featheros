"""Unit and integration tests for FeatherRun core engine (Phase 1)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from contextlib import redirect_stdout

from featheros.bottles import BottleManager
from featheros.cli import main as cli_main
from featheros.pe_inspector import OLE2_MAGIC, inspect_binary
from featheros.shortcuts import (
    LNK_CLSID,
    LNK_HEADER_SIZE,
    HAS_ARGUMENTS,
    HAS_LINK_INFO,
    IS_UNICODE,
    discover_bottle_shortcuts,
    parse_lnk_target,
    prune_bottle_shortcuts,
    sync_bottle_shortcuts,
)
from featheros.system_probe import SystemProbe, probe_system


def make_synthetic_pe(
    path: Path,
    *,
    machine: int = 0x8664,
    opt_magic: int = 0x20B,
    subsystem: int = 2,
    characteristics: int = 0x0002,
    payload: bytes = b"",
) -> Path:
    """Generate a minimal structurally valid Windows PE executable."""
    pe_offset = 0x80
    dos_header = bytearray(pe_offset)
    dos_header[0:2] = b"MZ"
    struct.pack_into("<I", dos_header, 0x3C, pe_offset)

    pe_sig = b"PE\x00\x00"
    opt_hdr_size = 96
    coff_header = struct.pack(
        "<HHIIIHH",
        machine,
        1,  # NumberOfSections
        0,  # TimeDateStamp
        0,  # PointerToSymbolTable
        0,  # NumberOfSymbols
        opt_hdr_size,
        characteristics,
    )
    opt_header = bytearray(opt_hdr_size)
    struct.pack_into("<H", opt_header, 0, opt_magic)
    struct.pack_into("<H", opt_header, 68, subsystem)

    path.write_bytes(bytes(dos_header) + pe_sig + coff_header + bytes(opt_header) + payload)
    return path


def make_synthetic_lnk(path: Path, target_win_path: str, arguments: str = "") -> Path:
    """Generate a structurally valid MS-SHLLINK (.lnk) file with LinkInfo + optional args."""
    flags = HAS_LINK_INFO | IS_UNICODE
    if arguments:
        flags |= HAS_ARGUMENTS

    header = bytearray(LNK_HEADER_SIZE)
    struct.pack_into("<I", header, 0, LNK_HEADER_SIZE)
    header[4:20] = LNK_CLSID
    struct.pack_into("<I", header, 20, flags)

    # LinkInfo block with LocalBasePath
    local_base_bytes = target_win_path.encode("latin-1") + b"\x00"
    suffix_bytes = b"\x00"
    header_len = 28
    volume_id_offset = header_len
    volume_id = struct.pack("<IIII", 16, 3, 0, 16)  # minimal VolumeID
    local_base_offset = volume_id_offset + len(volume_id)
    common_suffix_offset = local_base_offset + len(local_base_bytes)
    total_info_size = common_suffix_offset + len(suffix_bytes)

    link_info = (
        struct.pack(
            "<IIIIIII",
            total_info_size,
            header_len,
            0x00000001,  # VolumeIDAndLocalBasePath
            volume_id_offset,
            local_base_offset,
            0,  # CommonNetworkRelativeLinkOffset
            common_suffix_offset,
        )
        + volume_id
        + local_base_bytes
        + suffix_bytes
    )

    extra = b""
    if arguments:
        extra += struct.pack("<H", len(arguments)) + arguments.encode("utf-16-le")

    path.write_bytes(bytes(header) + link_info + extra)
    return path


def make_mock_probe(*, vulkan_hw: bool, gamemode: bool = True, mangohud: bool = False) -> SystemProbe:
    return SystemProbe(
        platform_system="Linux",
        machine="x86_64",
        cpu_count=4,
        ram_total_mb=8192,
        ram_available_mb=6400,
        wine_path="/usr/bin/wine",
        wine64_path="/usr/bin/wine64",
        wineserver_path="/usr/bin/wineserver",
        winetricks_path="/usr/bin/winetricks",
        steam_path="/usr/games/steam",
        gamemoderun_path="/usr/bin/gamemoderun" if gamemode else None,
        mangohud_path="/usr/bin/mangohud" if mangohud else None,
        multiarch_i386=True,
        vulkan_hardware_ready=vulkan_hw,
        vulkan_device_name="AMD Radeon RX" if vulkan_hw else "llvmpipe (LLVM)",
        vulkan_software_only=not vulkan_hw,
        dxvk_available=True,
        vkd3d_available=True,
    )


class TestPEInspector(unittest.TestCase):
    def test_pe64_gui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = make_synthetic_pe(Path(tmp) / "notepad.exe", machine=0x8664, opt_magic=0x20B, subsystem=2)
            info = inspect_binary(exe)
            self.assertTrue(info.valid)
            self.assertEqual(info.file_type, "pe")
            self.assertEqual(info.arch, "x64")
            self.assertEqual(info.subsystem, "gui")
            self.assertFalse(info.is_installer)
            self.assertFalse(info.is_dll)

    def test_pe32_console_and_nsis_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            exe = make_synthetic_pe(
                Path(tmp) / "app_pkg.exe",
                machine=0x014C,
                opt_magic=0x10B,
                subsystem=3,
                payload=b"xxNullsoftInstxx",
            )
            info = inspect_binary(exe)
            self.assertTrue(info.valid)
            self.assertEqual(info.arch, "x86")
            self.assertEqual(info.subsystem, "console")
            self.assertTrue(info.is_installer)
            self.assertEqual(info.installer_kind, "nsis")

    def test_msi_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            msi = Path(tmp) / "tool.msi"
            msi.write_bytes(OLE2_MAGIC + b"\x00" * 128)
            info = inspect_binary(msi)
            self.assertTrue(info.valid)
            self.assertEqual(info.file_type, "msi")
            self.assertTrue(info.is_installer)
            self.assertEqual(info.installer_kind, "msi")

    def test_invalid_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "readme.txt"
            bad.write_text("not an exe", encoding="utf-8")
            info = inspect_binary(bad)
            self.assertFalse(info.valid)
            self.assertEqual(info.file_type, "unknown")

    def test_arm64_pe_rejected_on_x86_64(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            arm_exe = make_synthetic_pe(Path(tmp) / "armapp.exe", machine=0xAA64, opt_magic=0x20B, subsystem=2)
            info = inspect_binary(arm_exe)
            self.assertFalse(info.valid)
            self.assertEqual(info.arch, "arm64")
            self.assertIn("Unsupported", info.error or "")


class TestSystemProbe(unittest.TestCase):
    def test_probe_hardware_vulkan_and_meminfo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meminfo = Path(tmp) / "meminfo"
            meminfo.write_text("MemTotal:        4096000 kB\nMemAvailable:    3072000 kB\n", encoding="utf-8")

            def fake_which(name: str) -> str | None:
                return f"/usr/bin/{name}" if name in ("wine", "vulkaninfo", "dpkg") else None

            def fake_run(cmd: list[str]) -> tuple[int, str]:
                if "vulkaninfo" in cmd[0]:
                    return 0, "deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU\ndeviceName = Intel UHD Graphics\n"
                if "dpkg" in cmd[0]:
                    return 0, "i386\n"
                return 1, ""

            probe = probe_system(which=fake_which, run_cmd=fake_run, meminfo_path=meminfo)
            self.assertEqual(probe.ram_total_mb, 4000)
            self.assertEqual(probe.ram_available_mb, 3000)
            self.assertTrue(probe.multiarch_i386)
            self.assertTrue(probe.vulkan_hardware_ready)
            self.assertFalse(probe.vulkan_software_only)
            self.assertEqual(probe.vulkan_device_name, "Intel UHD Graphics")

    def test_probe_vm_software_vulkan_falls_back(self) -> None:
        def fake_which(name: str) -> str | None:
            return f"/usr/bin/{name}" if name in ("wine", "vulkaninfo") else None

        def fake_run(cmd: list[str]) -> tuple[int, str]:
            return 0, "deviceType = PHYSICAL_DEVICE_TYPE_CPU\ndeviceName = llvmpipe (LLVM 19.0)\n"

        probe = probe_system(which=fake_which, run_cmd=fake_run, meminfo_path=Path("/nonexistent"))
        self.assertFalse(probe.vulkan_hardware_ready)
        self.assertTrue(probe.vulkan_software_only)
        self.assertEqual(probe.recommended_graphics_backend, "wined3d")


class TestBottleManagerAndLaunchPlan(unittest.TestCase):
    def test_dxvk_enabled_on_hw_gpu_and_fallback_in_vm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BottleManager(home=Path(tmp) / "feather")
            exe = make_synthetic_pe(Path(tmp) / "game.exe")

            plan_hw = mgr.build_launch_plan(exe, bottle_name="gaming", probe=make_mock_probe(vulkan_hw=True))
            self.assertEqual(plan_hw.effective_backend, "dxvk+vkd3d")
            self.assertIn("d3d11=n,b", plan_hw.env["WINEDLLOVERRIDES"])
            self.assertNotIn("PROTON_USE_WINED3D", plan_hw.env)
            self.assertEqual(plan_hw.notices, [])

            plan_vm = mgr.build_launch_plan(exe, bottle_name="gaming", probe=make_mock_probe(vulkan_hw=False))
            self.assertEqual(plan_vm.effective_backend, "wined3d")
            self.assertIn("d3d11=b", plan_vm.env["WINEDLLOVERRIDES"])
            self.assertEqual(plan_vm.env["PROTON_USE_WINED3D"], "1")
            self.assertTrue(any("VM-safe mode" in n for n in plan_vm.notices))

    def test_msi_and_virtual_desktop_and_gamemode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BottleManager(home=Path(tmp) / "feather")
            mgr.create_bottle(
                "Legacy App",
                windows_version="win7",
                virtual_desktop="1024x768",
                gamemode=True,
            )
            msi = Path(tmp) / "legacy.msi"
            msi.write_bytes(OLE2_MAGIC + b"\x00" * 64)

            plan = mgr.build_launch_plan(
                msi,
                bottle_name="legacy-app",
                probe=make_mock_probe(vulkan_hw=True, gamemode=True),
            )
            self.assertEqual(plan.command[0], "/usr/bin/gamemoderun")
            self.assertIn("explorer", plan.command)
            self.assertIn("/desktop=legacy-app,1024x768", plan.command)
            self.assertIn("msiexec", plan.command)
            self.assertIn("/i", plan.command)

    def test_isolated_bottle_and_winetricks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mgr = BottleManager(home=Path(tmp) / "feather")
            exe = make_synthetic_pe(Path(tmp) / "MyCoolTool.exe")
            plan = mgr.build_launch_plan(exe, isolated=True, probe=make_mock_probe(vulkan_hw=True))
            self.assertEqual(plan.bottle.slug, "mycooltool")

            cmd, env = mgr.build_winetricks_command("mycooltool", ["vcrun2022", "corefonts"])
            self.assertEqual(cmd, ["winetricks", "-q", "vcrun2022", "corefonts"])
            self.assertTrue(env["WINEPREFIX"].endswith("prefix"))

            # Verify apply_settings generates real winecfg + LogPixels DPI commands
            mgr.update_bottle("mycooltool", windows_version="win11", dpi=120)
            cmds, _senv = mgr.build_apply_settings_commands("mycooltool", probe=make_mock_probe(vulkan_hw=True))
            self.assertTrue(any("winecfg" in c and "win11" in c for c in cmds))
            self.assertTrue(any("LogPixels" in c and "120" in c for c in cmds))


class TestShortcutsAndLnkParser(unittest.TestCase):
    def test_lnk_parsing_and_desktop_sync_and_prune(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "feather"
            apps_dir = Path(tmp) / "applications"
            mgr = BottleManager(home=home)
            mgr.create_bottle("office")
            drive_c = mgr.prefix_dir("office") / "drive_c"

            # Create real app exe + ignored uninstaller
            app_dir = drive_c / "Program Files" / "NoteApp"
            app_dir.mkdir(parents=True)
            exe = make_synthetic_pe(app_dir / "NoteApp.exe")
            make_synthetic_pe(app_dir / "unins000.exe")

            # Create Start Menu .lnk pointing to NoteApp.exe with an argument
            lnk_path = (
                drive_c
                / "ProgramData"
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "NoteApp Pro.lnk"
            )
            make_synthetic_lnk(lnk_path, r"C:\Program Files\NoteApp\NoteApp.exe", "--portable")

            target, args = parse_lnk_target(lnk_path)
            self.assertEqual(target, r"C:\Program Files\NoteApp\NoteApp.exe")
            self.assertEqual(args, "--portable")

            discovered = discover_bottle_shortcuts(mgr, "office")
            self.assertEqual(len(discovered), 1)
            self.assertEqual(discovered[0].name, "NoteApp Pro")
            self.assertEqual(discovered[0].target_path, exe.resolve())

            written = sync_bottle_shortcuts(mgr, "office", applications_dir=apps_dir)
            self.assertEqual(len(written), 1)
            desktop_text = written[0].read_text(encoding="utf-8")
            self.assertIn("Name=NoteApp Pro", desktop_text)
            self.assertIn("feather-run", desktop_text)
            self.assertIn("--portable", desktop_text)

            removed = prune_bottle_shortcuts("office", applications_dir=apps_dir)
            self.assertEqual(len(removed), 1)
            self.assertFalse(written[0].exists())


class TestCLI(unittest.TestCase):
    def test_cli_lifecycle_and_dry_run_shorthand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = str(Path(tmp) / "feather")
            exe = make_synthetic_pe(Path(tmp) / "PaintTool.exe")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--home", home, "inspect", str(exe), "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["arch"], "x64")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--home", home, "bottles", "create", "Studio", "--windows-version", "win11", "--json"])
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue())["slug"], "studio")

            # Shorthand invocation (`feather-run app.exe --dry-run`)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli_main(["--home", home, "--bottle", "studio", "--dry-run", str(exe)])
            self.assertEqual(rc, 0)
            plan = json.loads(buf.getvalue())
            self.assertEqual(plan["bottle"]["slug"], "studio")
            self.assertIn(str(exe.resolve()), plan["command"])


if __name__ == "__main__":
    unittest.main()
