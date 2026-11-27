#!/usr/bin/env bash
# Boot FeatherOS Live ISO in QEMU on Linux / WSL2
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ISO_PATH="${1:-${REPO_ROOT}/dist/featheros-0.4.0-amd64.iso}"
RAM_MB="${RAM_MB:-2048}"
CPUS="${CPUS:-2}"
DISK_PATH="${DISK_PATH:-}"

if [ ! -f "${ISO_PATH}" ]; then
  echo "Error: ISO not found at '${ISO_PATH}'." >&2
  echo "Build it with: sudo ./build/build-iso.sh" >&2
  exit 1
fi

if ! command -v qemu-system-x86_64 >/dev/null 2>&1; then
  echo "Error: qemu-system-x86_64 not installed." >&2
  exit 1
fi

ACCEL_ARGS=(-accel tcg)
if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then
  ACCEL_ARGS=(-enable-kvm -cpu host)
fi

DISK_ARGS=()
if [ -n "${DISK_PATH}" ] && [ -f "${DISK_PATH}" ]; then
  DISK_ARGS=(-drive "file=${DISK_PATH},format=qcow2,if=virtio")
fi

echo "Launching FeatherOS in QEMU (${RAM_MB} MB RAM, ${CPUS} vCPUs)..."
exec qemu-system-x86_64 \
  "${ACCEL_ARGS[@]}" \
  -m "${RAM_MB}" \
  -smp "${CPUS}" \
  -cdrom "${ISO_PATH}" \
  -boot d \
  -vga virtio \
  -netdev user,id=net0 \
  -device virtio-net-pci,netdev=net0 \
  -usb \
  -device usb-tablet \
  "${DISK_ARGS[@]}"
