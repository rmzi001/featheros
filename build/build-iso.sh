#!/usr/bin/env bash
# FeatherOS Reproducible Hybrid UEFI + BIOS Live ISO Builder
# Runs on native Linux, WSL2 (Debian/Ubuntu), Docker, or GitHub Actions.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# shellcheck source=../config/featheros.conf
source "${REPO_ROOT}/config/featheros.conf"

WORK_DIR="${WORK_DIR:-${REPO_ROOT}/work}"
DIST_DIR="${DIST_DIR:-${REPO_ROOT}/dist}"
ROOTFS_DIR="${WORK_DIR}/rootfs"
ISO_STAGE="${WORK_DIR}/iso"
ISO_OUT="${DIST_DIR}/${ISO_FILENAME}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: build-iso.sh must be run as root (e.g., sudo ./build/build-iso.sh)." >&2
  exit 1
fi

REQUIRED_TOOLS=(debootstrap mksquashfs xorriso grub-mkstandalone mformat mcopy)
for tool in "${REQUIRED_TOOLS[@]}"; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Error: Required host tool '${tool}' not found." >&2
    echo "Install on Debian/Ubuntu: apt-get install debootstrap squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin grub-common mtools dosfstools" >&2
    exit 1
  fi
done

cleanup() {
  set +e
  for mnt in "${ROOTFS_DIR}/dev/pts" "${ROOTFS_DIR}/dev" "${ROOTFS_DIR}/proc" "${ROOTFS_DIR}/sys"; do
    if mountpoint -q "${mnt}" 2>/dev/null; then
      umount -lf "${mnt}"
    fi
  done
}
trap cleanup EXIT

echo "============================================================"
echo " Building ${OS_PRETTY_NAME} (${DEBIAN_SUITE} / ${DEBIAN_ARCH})"
echo " Output ISO: ${ISO_OUT}"
echo "============================================================"

rm -rf "${WORK_DIR}"
mkdir -p "${ROOTFS_DIR}" "${ISO_STAGE}/live" "${ISO_STAGE}/boot/grub" "${DIST_DIR}"

echo "[1/6] Bootstrapping minimal Debian (${DEBIAN_SUITE}) rootfs..."
DEBOOTSTRAP_ARGS=(--arch="${DEBIAN_ARCH}" --variant=minbase)
if [ -f /usr/share/keyrings/debian-archive-keyring.gpg ]; then
  DEBOOTSTRAP_ARGS+=(--keyring=/usr/share/keyrings/debian-archive-keyring.gpg)
fi
debootstrap "${DEBOOTSTRAP_ARGS[@]}" "${DEBIAN_SUITE}" "${ROOTFS_DIR}" "${DEBIAN_MIRROR}"

echo "[2/6] Staging FeatherOS configs, overlay, and FeatherRun package..."
STAGE_TMP="${ROOTFS_DIR}/tmp/featheros-build"
mkdir -p "${STAGE_TMP}"
cp "${REPO_ROOT}/config/featheros.conf" "${STAGE_TMP}/"
cp "${REPO_ROOT}/build/packages-core.list" "${STAGE_TMP}/"
cp "${REPO_ROOT}/build/packages-optional.list" "${STAGE_TMP}/"
cp "${REPO_ROOT}/build/chroot-setup.sh" "${STAGE_TMP}/"
cp -a "${REPO_ROOT}/desktop/overlay" "${STAGE_TMP}/overlay"
cp -a "${REPO_ROOT}/compat" "${STAGE_TMP}/compat"
chmod +x "${STAGE_TMP}/chroot-setup.sh"

echo "[3/6] Mounting virtual filesystems and running chroot provisioning..."
mount --bind /dev "${ROOTFS_DIR}/dev"
mount --bind /dev/pts "${ROOTFS_DIR}/dev/pts"
mount -t proc proc "${ROOTFS_DIR}/proc"
mount -t sysfs sysfs "${ROOTFS_DIR}/sys"
cp /etc/resolv.conf "${ROOTFS_DIR}/etc/resolv.conf"

chroot "${ROOTFS_DIR}" /tmp/featheros-build/chroot-setup.sh
cleanup

echo "[4/6] Extracting kernel and initramfs..."
VMLINUZ="$(find "${ROOTFS_DIR}/boot" -maxdepth 1 -name 'vmlinuz-*' | sort -V | tail -n 1)"
INITRD="$(find "${ROOTFS_DIR}/boot" -maxdepth 1 -name 'initrd.img-*' | sort -V | tail -n 1)"
if [ -z "${VMLINUZ}" ] || [ -z "${INITRD}" ]; then
  echo "Error: Could not find kernel or initramfs inside rootfs /boot." >&2
  exit 1
fi
cp "${VMLINUZ}" "${ISO_STAGE}/live/vmlinuz"
cp "${INITRD}" "${ISO_STAGE}/live/initrd"

echo "[5/6] Compressing SquashFS (${SQUASHFS_COMP})..."
# Keep /boot inside filesystem.squashfs so Calamares unpackfs installs a bootable kernel & initramfs!
mksquashfs "${ROOTFS_DIR}" "${ISO_STAGE}/live/filesystem.squashfs" \
  -comp "${SQUASHFS_COMP}" -Xcompression-level 15

echo "[6/6] Generating hybrid UEFI + BIOS GRUB bootloaders and ISO..."
cat > "${ISO_STAGE}/boot/grub/grub.cfg" <<EOF
set default=0
set timeout=3

insmod all_video
insmod gfxterm

menuentry "${OS_PRETTY_NAME} — Live Desktop" {
    linux /live/vmlinuz boot=live components quiet splash console=tty0 console=ttyS0,115200n8
    initrd /live/initrd
}

menuentry "${OS_PRETTY_NAME} — Safe Graphics / VM Mode" {
    linux /live/vmlinuz boot=live components nomodeset console=tty0 console=ttyS0,115200n8
    initrd /live/initrd
}

menuentry "${OS_PRETTY_NAME} — Copy to RAM (Ultra Fast)" {
    linux /live/vmlinuz boot=live components toram quiet splash console=tty0 console=ttyS0,115200n8
    initrd /live/initrd
}
EOF

# Embedded GRUB config that locates the ISO/USB root reliably by file path
# Keep $prefix pointing at (memdisk)/boot/grub so insmod resolves embedded modules cleanly.
cat > "${WORK_DIR}/grub-embed.cfg" <<EOF
insmod iso9660
insmod part_msdos
insmod part_gpt
insmod fat
insmod search_fs_file
insmod search
insmod configfile
search --no-floppy --set=root --file /live/vmlinuz
configfile (\$root)/boot/grub/grub.cfg
EOF

# Build UEFI boot image
grub-mkstandalone \
  --format=x86_64-efi \
  --output="${WORK_DIR}/bootx64.efi" \
  --locales="" \
  --fonts="" \
  "boot/grub/grub.cfg=${WORK_DIR}/grub-embed.cfg"

dd if=/dev/zero of="${ISO_STAGE}/boot/grub/efiboot.img" bs=1M count=10
mformat -i "${ISO_STAGE}/boot/grub/efiboot.img" -F ::
mmd -i "${ISO_STAGE}/boot/grub/efiboot.img" ::/EFI ::/EFI/BOOT
mcopy -i "${ISO_STAGE}/boot/grub/efiboot.img" "${WORK_DIR}/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI

# Also mirror /EFI/BOOT/BOOTX64.EFI in the ISO tree for Windows USB tools (e.g. Rufus ISO mode)
mkdir -p "${ISO_STAGE}/EFI/BOOT"
cp "${WORK_DIR}/bootx64.efi" "${ISO_STAGE}/EFI/BOOT/BOOTX64.EFI"

# Build Legacy BIOS boot image with full module set required to locate /live/vmlinuz and boot Linux
grub-mkstandalone \
  --format=i386-pc \
  --output="${WORK_DIR}/core.img" \
  --install-modules="linux normal iso9660 biosdisk memdisk tar ls search search_label search_fs_file configfile part_msdos part_gpt fat ext2 all_video gfxterm font terminal echo test sleep boot vbe vga" \
  --modules="linux normal iso9660 biosdisk search search_fs_file configfile" \
  --locales="" \
  --fonts="" \
  "boot/grub/grub.cfg=${WORK_DIR}/grub-embed.cfg"

cat /usr/lib/grub/i386-pc/cdboot.img "${WORK_DIR}/core.img" > "${ISO_STAGE}/boot/grub/bios.img"

xorriso -as mkisofs \
  -iso-level 3 \
  -full-iso9660-filenames \
  -volid "${ISO_LABEL}" \
  -eltorito-boot boot/grub/bios.img \
    -no-emul-boot \
    -boot-load-size 4 \
    -boot-info-table \
    --eltorito-catalog boot/grub/boot.cat \
    --grub2-boot-info \
    --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
  -eltorito-alt-boot \
    -e boot/grub/efiboot.img \
    -no-emul-boot \
  -append_partition 2 0xef "${ISO_STAGE}/boot/grub/efiboot.img" \
  -output "${ISO_OUT}" \
  "${ISO_STAGE}"

sha256sum "${ISO_OUT}" > "${ISO_OUT}.sha256"

echo "============================================================"
echo " FeatherOS ISO ready: ${ISO_OUT}"
ls -lh "${ISO_OUT}"
cat "${ISO_OUT}.sha256"
echo "============================================================"
