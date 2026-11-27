"""feather-selftest: Automated in-OS QA Checking Agent for FeatherOS.

Runs inside a live booted FeatherOS session (or headless CI KVM VM) to verify
boot health, memory/zram efficiency, Windows .exe execution via Wine & FeatherRun,
desktop completeness, single Polkit agent integrity, Calamares disk-installer
readiness, and hygiene, producing an empirical 100-point QA scorecard.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Sequence

from . import __codename__, __codename_display__, __version__
from .system_probe import SystemProbe, probe_system

CommandRunner = Callable[[list[str], int], tuple[int, str]]
WhichLookup = Callable[[str], str | None]

ESSENTIAL_BINARIES: tuple[str, ...] = (
    "thunar",
    "xfwm4",
    "xfce4-panel",
    "xfdesktop",
    "xfce4-terminal",
    "xfce4-taskmanager",
    "xfce4-screenshooter",
    "mousepad",
    "ristretto",
    "firefox-esr",
    "wine",
    "grub-install",
    "efibootmgr",
    "ntfs-3g",
    "unsquashfs",
    "rsync",
    "calamares",
    "feather-run",
    "feather-compat",
    "feather-settings",
    "feather-store",
    "feather-ctl",
)


@dataclass(frozen=True)
class CheckResult:
    """Single empirical QA check inside FeatherOS."""

    id: str
    category: str
    passed: bool
    weight: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _default_run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    env = os.environ.copy()
    if cmd and "wine" in Path(cmd[0]).name.lower():
        env.setdefault("WINEDEBUG", "-all")
        env.setdefault("WINEDLLOVERRIDES", "mscoree,mshtml=")
        if not env.get("WINEPREFIX"):
            default_pfx = Path.home() / ".local" / "share" / "featheros" / "bottles" / "default" / "prefix"
            if default_pfx.is_dir():
                env["WINEPREFIX"] = str(default_pfx)
        xauth = env.get("XAUTHORITY", "")
        if env.get("DISPLAY") and xauth and not Path(xauth).is_file():
            env.pop("DISPLAY", None)
        xdg = env.get("XDG_RUNTIME_DIR", "")
        if not xdg or not Path(xdg).is_dir():
            rt_dir = Path(tempfile.gettempdir()) / f"feather-xdg-{os.getuid() if hasattr(os, 'getuid') else 0}"
            rt_dir.mkdir(parents=True, exist_ok=True)
            try:
                rt_dir.chmod(0o700)
            except OSError:
                pass
            env["XDG_RUNTIME_DIR"] = str(rt_dir)
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def _find_binary(name: str, which: WhichLookup, root: Path) -> str | None:
    found = which(name)
    if found:
        return found
    if which is shutil.which:
        for sub in ("usr/sbin", "sbin", "usr/bin", "bin", "usr/local/bin"):
            candidate = root / sub / name
            if candidate.is_file():
                return str(candidate)
    return None


def _count_enabled_polkit_autostarts(root: Path) -> list[str]:
    """Return active Polkit agent .desktop filenames in /etc/xdg/autostart."""
    autostart_dir = root / "etc" / "xdg" / "autostart"
    if not autostart_dir.is_dir():
        return []
    active: list[str] = []
    for df in sorted(autostart_dir.glob("*.desktop")):
        text = df.read_text(encoding="utf-8", errors="ignore")
        low = text.lower()
        if not any(tok in low for tok in ("polkit", "lxpolkit")):
            continue
        if "hidden=true" in low or "nodisplay=true" in low and "exec=" not in low:
            continue
        # Respect explicit Hidden=true in .desktop
        if any(ln.strip().lower() == "hidden=true" for ln in text.splitlines()):
            continue
        active.append(df.name)
    return active


def run_selftest(
    *,
    run_cmd: CommandRunner = _default_run,
    which: WhichLookup = shutil.which,
    root: Path = Path("/"),
    probe: SystemProbe | None = None,
    run_wine_smoke: bool = True,
) -> dict[str, Any]:
    """Execute all empirical FeatherOS health checks and compute a 100-point score."""
    sys_probe = probe or probe_system(which=which)
    checks: list[CheckResult] = []

    # 1. OS Identity (8 pts)
    os_release = root / "etc" / "os-release"
    issue_file = root / "etc" / "issue"
    rel_text = os_release.read_text(encoding="utf-8", errors="ignore") if os_release.is_file() else ""
    iss_text = issue_file.read_text(encoding="utf-8", errors="ignore") if issue_file.is_file() else ""
    id_ok = "FeatherOS" in rel_text and "FeatherOS" in iss_text
    checks.append(
        CheckResult(
            id="os_identity",
            category="branding",
            passed=id_ok,
            weight=8,
            detail="FeatherOS branding present in /etc/os-release and /etc/issue"
            if id_ok
            else "Missing FeatherOS branding in /etc/os-release or /etc/issue",
        )
    )

    # 2. Zero failed systemd units (10 pts)
    if which("systemctl"):
        rc, out = run_cmd(["systemctl", "--failed", "--no-legend", "--plain"], 10)
        failed_lines = [ln for ln in out.splitlines() if ln.strip()]
        systemd_ok = rc == 0 and len(failed_lines) == 0
        detail = "0 failed systemd units" if systemd_ok else f"Failed units: {'; '.join(failed_lines[:3])}"
    else:
        systemd_ok = False
        detail = "systemctl not available"
    checks.append(
        CheckResult(
            id="systemd_clean",
            category="boot",
            passed=systemd_ok,
            weight=10,
            detail=detail,
        )
    )

    # 3. Active zram compressed swap (8 pts)
    swapon_bin = _find_binary("swapon", which, root)
    if swapon_bin:
        rc, out = run_cmd([swapon_bin, "--show", "--noheadings"], 5)
        zram_ok = rc == 0 and "zram" in out
        zdetail = out.splitlines()[0] if zram_ok and out else "zram swap not active"
    else:
        zram_ok = False
        zdetail = "swapon not available"
    checks.append(CheckResult("zram_active", "performance", zram_ok, 8, zdetail))

    # 4. Memory footprint (10 pts)
    ram_total = sys_probe.ram_total_mb
    ram_avail = sys_probe.ram_available_mb
    if ram_total is not None and ram_avail is not None:
        used_mb = max(0, ram_total - ram_avail)
        ram_ok = used_mb <= 750
        ram_detail = f"{used_mb} MB used / {ram_total} MB total ({ram_avail} MB available)"
    else:
        ram_ok = False
        ram_detail = "Unable to read /proc/meminfo"
    checks.append(CheckResult("ram_footprint", "performance", ram_ok, 10, ram_detail))

    # 5. Desktop & installer binaries completeness (14 pts)
    missing_bins = [b for b in ESSENTIAL_BINARIES if _find_binary(b, which, root) is None]
    bins_ok = len(missing_bins) == 0
    checks.append(
        CheckResult(
            id="essential_apps",
            category="completeness",
            passed=bins_ok,
            weight=14,
            detail=f"All {len(ESSENTIAL_BINARIES)} core OS, desktop & installer binaries present"
            if bins_ok
            else f"Missing binaries: {', '.join(missing_bins)}",
        )
    )

    # 6. Dual Windows 11 Dark & Light themes installed (8 pts)
    dark_css = root / "usr" / "share" / "themes" / "FeatherWin11-Dark" / "gtk-3.0" / "gtk.css"
    light_css = root / "usr" / "share" / "themes" / "FeatherWin11-Light" / "gtk-3.0" / "gtk.css"
    dark_wm = root / "usr" / "share" / "themes" / "FeatherWin11-Dark" / "xfwm4" / "themerc"
    light_wm = root / "usr" / "share" / "themes" / "FeatherWin11-Light" / "xfwm4" / "themerc"
    themes_ok = dark_css.is_file() and light_css.is_file() and dark_wm.is_file() and light_wm.is_file()
    checks.append(
        CheckResult(
            id="fluent_themes",
            category="ui",
            passed=themes_ok,
            weight=8,
            detail="FeatherWin11-Dark & FeatherWin11-Light GTK3 + XFWM4 themes installed"
            if themes_ok
            else "One or more FeatherWin11 Dark/Light theme assets missing",
        )
    )

    # 7. Single Polkit auth agent installed & no duplicate autostart collision (8 pts)
    polkit_autostarts = _count_enabled_polkit_autostarts(root)
    polkit_candidates = (
        root / "usr" / "lib" / "x86_64-linux-gnu" / "polkit-mate-authentication-agent-1",
        root / "usr" / "lib" / "mate-polkit" / "polkit-mate-authentication-agent-1",
        root / "usr" / "lib" / "policykit-1-gnome" / "polkit-gnome-authentication-agent-1",
    )
    polkit_bin = any(p.is_file() for p in polkit_candidates) or _find_binary("lxpolkit", which, root) is not None
    polkit_ok = polkit_bin and len(polkit_autostarts) == 1
    polkit_detail = (
        f"Single Polkit agent configured cleanly ({polkit_autostarts[0]})"
        if polkit_ok
        else f"Polkit defect: bin={polkit_bin}, active_autostarts={polkit_autostarts}"
    )
    checks.append(
        CheckResult(
            id="polkit_agent",
            category="security",
            passed=polkit_ok,
            weight=8,
            detail=polkit_detail,
        )
    )

    # 8. Calamares disk installer readiness (10 pts)
    boot_dir = root / "boot"
    has_kernel = boot_dir.is_dir() and any(boot_dir.glob("vmlinuz-*"))
    has_qml = (root / "etc" / "calamares" / "branding" / "featheros" / "show.qml").is_file()
    has_cleanup = (root / "etc" / "calamares" / "modules" / "removeuser.conf").is_file()
    users_conf = root / "etc" / "calamares" / "modules" / "users.conf"
    has_users = users_conf.is_file() and "sudoersGroup: sudo" in users_conf.read_text(encoding="utf-8", errors="ignore")
    pkgs_conf = root / "etc" / "calamares" / "modules" / "packages.conf"
    pkgs_safe = pkgs_conf.is_file() and "try_remove:" in pkgs_conf.read_text(encoding="utf-8", errors="ignore")
    has_grub_def = (root / "etc" / "default" / "grub").is_file()
    cal_bins = all(_find_binary(b, which, root) is not None for b in ("calamares", "unsquashfs", "rsync", "grub-install"))
    cal_ok = has_kernel and has_qml and has_cleanup and has_users and pkgs_safe and has_grub_def and cal_bins
    checks.append(
        CheckResult(
            id="calamares_ready",
            category="installer",
            passed=cal_ok,
            weight=10,
            detail="Kernel in /boot, unsquashfs, rsync, grub-install, /etc/default/grub, users.conf, try_remove & QML ready"
            if cal_ok
            else (
                f"Incomplete installer: kernel={has_kernel}, qml={has_qml}, cleanup={has_cleanup}, "
                f"users={has_users}, try_remove={pkgs_safe}, default_grub={has_grub_def}, bins={cal_bins}"
            ),
        )
    )

    # 9. Wine + 32-bit i386 multiarch readiness (10 pts)
    wine_ok = sys_probe.can_run_wine and sys_probe.multiarch_i386
    checks.append(
        CheckResult(
            id="wine_multiarch",
            category="windows_compat",
            passed=wine_ok,
            weight=10,
            detail=f"Wine={sys_probe.wine_path or sys_probe.wine64_path}, i386={sys_probe.multiarch_i386}"
            if wine_ok
            else f"Missing Wine or i386 multiarch (wine={sys_probe.can_run_wine}, i386={sys_probe.multiarch_i386})",
        )
    )

    # 10. Live Win32 execution smoke test via Wine cmd.exe (10 pts)
    if run_wine_smoke and sys_probe.can_run_wine:
        wine_bin = sys_probe.wine_path or sys_probe.wine64_path or "wine"
        rc, out = run_cmd([wine_bin, "cmd", "/c", "echo", "FEATHEROS_WIN32_OK"], 45)
        win32_ok = rc == 0 and "FEATHEROS_WIN32_OK" in out
        win32_detail = "Win32 cmd.exe returned FEATHEROS_WIN32_OK" if win32_ok else f"rc={rc}: {out[:400]}"
    elif not run_wine_smoke:
        win32_ok = sys_probe.can_run_wine
        win32_detail = "Skipped live Wine exec (--quick); Wine binary detected"
    else:
        win32_ok = False
        win32_detail = "Wine binary not available"
    checks.append(CheckResult("win32_smoke_exec", "windows_compat", win32_ok, 10, win32_detail))

    # 11. Zero leftover v0.1 Openbox/Tint2/PCManFM configs (4 pts)
    obsolete = [
        root / "etc" / "xdg" / "openbox" / "rc.xml",
        root / "etc" / "xdg" / "tint2" / "tint2rc",
        root / "etc" / "xdg" / "jgmenu" / "jgmenurc",
    ]
    clean_ok = not any(p.exists() for p in obsolete)
    checks.append(
        CheckResult(
            id="no_legacy_debt",
            category="hygiene",
            passed=clean_ok,
            weight=4,
            detail="No legacy Openbox/Tint2/jgmenu overlay files present"
            if clean_ok
            else "Legacy v0.1 Openbox/Tint2/jgmenu files still present",
        )
    )

    total_weight = sum(c.weight for c in checks)
    earned = sum(c.weight for c in checks if c.passed)
    score = round(earned * 100 / total_weight) if total_weight else 0

    return {
        "os": "FeatherOS",
        "version": __version__,
        "codename": __codename__,
        "score": score,
        "earned": earned,
        "max_score": total_weight,
        "passed_count": sum(1 for c in checks if c.passed),
        "total_checks": len(checks),
        "checks": [c.to_dict() for c in checks],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="feather-selftest",
        description="FeatherOS Automated In-OS QA Checking Agent",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON scorecard")
    parser.add_argument("--quick", action="store_true", help="Skip live Wine cmd.exe execution")
    parser.add_argument(
        "--min-score",
        type=int,
        default=0,
        help="Exit non-zero if score is below threshold",
    )
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    report = run_selftest(run_wine_smoke=not args.quick)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== FEATHEROS QA CHECKING AGENT (v{__version__} {__codename_display__}) ===")
        for chk in report["checks"]:
            mark = "PASS" if chk["passed"] else "FAIL"
            print(f"  [{mark}] ({chk['weight']:2d} pts) {chk['id']:18s} — {chk['detail']}")
        print(
            f"FEATHEROS_SELFTEST_SCORE: {report['score']}/100 "
            f"({report['passed_count']}/{report['total_checks']} checks passed)"
        )
    return 0 if report["score"] >= args.min_score else 1


if __name__ == "__main__":
    raise SystemExit(main())
