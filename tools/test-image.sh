#!/usr/bin/env bash
set -euo pipefail

image=${1:?usage: tools/test-image.sh IMAGE}
command -v qemu-system-x86_64 >/dev/null || { echo "qemu-system-x86_64 is required" >&2; exit 2; }
qemu_args=(-m 2048 -boot d -cdrom "$image" -nic user,hostfwd=tcp:127.0.0.1:6022-:22 -display none -serial stdio)
if [ -e /dev/kvm ]; then
  qemu_args=(-enable-kvm "${qemu_args[@]}")
else
  echo "warning: /dev/kvm unavailable; using software emulation" >&2
fi
exec qemu-system-x86_64 "${qemu_args[@]}"
