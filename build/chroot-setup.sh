#!/usr/bin/env bash
# FeatherOS v0.3.0 chroot provisioning script (runs inside target Debian rootfs)
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export LC_ALL=C

BUILD_TMP="/tmp/featheros-build"
# shellcheck source=../config/featheros.conf
source "${BUILD_TMP}/featheros.conf"

echo "[FeatherOS chroot] Configuring hostname and apt repositories (${DEBIAN_SUITE})..."
echo "${LIVE_HOSTNAME}" > /etc/hostname
mkdir -p /etc/network

cat > /etc/apt/sources.list <<EOF
deb ${DEBIAN_MIRROR} ${DEBIAN_SUITE} main contrib non-free non-free-firmware
deb ${DEBIAN_MIRROR} ${DEBIAN_SUITE}-updates main contrib non-free non-free-firmware
EOF

if [ "${ENABLE_MULTIARCH_I386}" = "true" ]; then
  echo "[FeatherOS chroot] Enabling i386 multiarch for 32-bit Windows software..."
  dpkg --add-architecture i386
fi

apt-get update

read_pkg_list() {
  grep -Ev '^\s*(#|$)' "$1"
}

echo "[FeatherOS chroot] Installing core XFCE 4.20 + Wine + GRUB2 packages (--no-install-recommends)..."
mapfile -t CORE_PKGS < <(read_pkg_list "${BUILD_TMP}/packages-core.list")
apt-get install -y --no-install-recommends "${CORE_PKGS[@]}"

echo "[FeatherOS chroot] Ensuring Wine 64-bit & 32-bit runtime libraries (with recommends)..."
apt-get install -y wine wine64 wine32:i386

echo "[FeatherOS chroot] Installing optional apps, Bluetooth, firmware, Calamares & gaming extras..."
mapfile -t OPT_PKGS < <(read_pkg_list "${BUILD_TMP}/packages-optional.list")
for pkg in "${OPT_PKGS[@]}"; do
  if apt-cache show "${pkg}" >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends "${pkg}" || \
      echo "[FeatherOS chroot] Warning: optional package '${pkg}' failed to install; continuing."
  else
    echo "[FeatherOS chroot] Skipping unavailable optional package: ${pkg}"
  fi
done

echo "[FeatherOS chroot] Applying FeatherShell v0.3 Windows 11 Dark/Light Glass overlay..."
cp -a "${BUILD_TMP}/overlay/." /
cp -f /etc/featheros-release /etc/os-release
chmod 0755 \
  /usr/local/bin/feather-firstboot \
  /usr/local/bin/feather-polkit-agent \
  /usr/local/bin/feather-calamares \
  /usr/local/bin/feather-boot-report

echo "[FeatherOS chroot] Installing FeatherRun / FeatherCompat / FeatherSettings / FeatherStore / FeatherCtl / FeatherSelftest..."
rm -rf /usr/lib/python3/dist-packages/featheros
cp -a "${BUILD_TMP}/compat/featheros" /usr/lib/python3/dist-packages/featheros

cat > /usr/local/bin/feather-run <<'EOF'
#!/usr/bin/env python3
from featheros.cli import main
raise SystemExit(main())
EOF

cat > /usr/local/bin/feather-compat <<'EOF'
#!/usr/bin/env python3
from featheros.compat_gui import main
raise SystemExit(main())
EOF

cat > /usr/local/bin/feather-ctl <<'EOF'
#!/usr/bin/env python3
from featheros.ctl import main
raise SystemExit(main())
EOF

cat > /usr/local/bin/feather-store <<'EOF'
#!/usr/bin/env python3
from featheros.store import main
raise SystemExit(main())
EOF

cat > /usr/local/bin/feather-settings <<'EOF'
#!/usr/bin/env python3
from featheros.settings_hub import main
raise SystemExit(main())
EOF

cat > /usr/local/bin/feather-selftest <<'EOF'
#!/usr/bin/env python3
from featheros.selftest import main
raise SystemExit(main())
EOF

chmod 0755 \
  /usr/local/bin/feather-run \
  /usr/local/bin/feather-compat \
  /usr/local/bin/feather-ctl \
  /usr/local/bin/feather-store \
  /usr/local/bin/feather-settings \
  /usr/local/bin/feather-selftest

echo "[FeatherOS chroot] Configuring live user '${LIVE_USER}'..."
if ! id -u "${LIVE_USER}" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo,audio,video,netdev,plugdev "${LIVE_USER}"
fi
echo "${LIVE_USER}:${LIVE_USER}" | chpasswd
echo "root:feather" | chpasswd
echo "${LIVE_USER} ALL=(ALL) NOPASSWD: ALL" > "/etc/sudoers.d/90-${LIVE_USER}"
chmod 0440 "/etc/sudoers.d/90-${LIVE_USER}"

# Apply Windows 11 Dark/Light Glass skeleton configs to live user home
cp -a /etc/skel/. "/home/${LIVE_USER}/"
chown -R "${LIVE_USER}:${LIVE_USER}" "/home/${LIVE_USER}"

echo "[FeatherOS chroot] Smoke-testing live Wine Win32 cmd.exe execution as '${LIVE_USER}'..."
su -s /bin/bash "${LIVE_USER}" -c '
  set -euo pipefail
  TMP_W="$(mktemp -d)"
  TMP_R="$(mktemp -d)"
  chmod 0700 "$TMP_R"
  trap "rm -rf \"$TMP_W\" \"$TMP_R\"" EXIT
  export WINEPREFIX="$TMP_W"
  export XDG_RUNTIME_DIR="$TMP_R"
  export WINEDLLOVERRIDES="mscoree,mshtml="
  export WINEDEBUG="-all"
  unset DISPLAY
  OUT="$(wine cmd /c echo FEATHEROS_WIN32_OK 2>&1 || true)"
  echo "[FeatherOS chroot] Wine smoke output: ${OUT}"
  if ! printf "%s\n" "${OUT}" | grep -q "FEATHEROS_WIN32_OK"; then
    echo "[FeatherOS chroot] Wine smoke failed; collecting diagnostics..." >&2
    WINEDEBUG="err+all" wine cmd /c echo FEATHEROS_WIN32_OK || true
    ls -la /usr/lib/wine /usr/lib/x86_64-linux-gnu/wine /usr/lib/i386-linux-gnu/wine 2>/dev/null || true
    exit 1
  fi
'

echo "[FeatherOS chroot] Configuring locales, fast-boot services, Plymouth, icons & MIME database..."
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen || true
locale-gen || true
echo 'LANG=en_US.UTF-8' > /etc/default/locale

systemctl enable lightdm NetworkManager zramswap feather-boot-report || true
systemctl enable bluetooth || true

# Disable slow background timers during live boot for snappier responsiveness
systemctl disable apt-daily.timer apt-daily-upgrade.timer man-db.timer dpkg-db-backup.timer fstrim.timer 2>/dev/null || true

if command -v plymouth-set-default-theme >/dev/null 2>&1; then
  plymouth-set-default-theme featheros || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor || true
fi

update-desktop-database /usr/share/applications || true
update-mime-database /usr/share/mime || true
update-initramfs -u || true

echo "[FeatherOS chroot] Cleaning apt caches and temporary build files..."
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* "${BUILD_TMP}"
echo "[FeatherOS chroot] Provisioning complete."
