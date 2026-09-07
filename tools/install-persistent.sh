#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 --device /dev/sdX --confirm-device /dev/sdX --yes [--squashfs FILE] [--hostname NAME]" >&2
  exit 2
}

device=""; confirm=""; squashfs="/run/archiso/bootmnt/drone/x86_64/airootfs.sfs"; hostname_value="mcp-drone"; yes="false"
while [ "$#" -gt 0 ]; do
  case "$1" in
    --device) device=${2:?missing device}; shift 2 ;;
    --confirm-device) confirm=${2:?missing confirmation}; shift 2 ;;
    --squashfs) squashfs=${2:?missing squashfs}; shift 2 ;;
    --hostname) hostname_value=${2:?missing hostname}; shift 2 ;;
    --yes) yes="true"; shift ;;
    *) usage ;;
  esac
done

[ "$yes" = "true" ] && [ -n "$device" ] && [ "$confirm" = "$device" ] || { echo "refusing install: pass --yes and --confirm-device with the exact target" >&2; exit 2; }
[ "${device#/dev/}" != "$device" ] || { echo "target must be a /dev disk" >&2; exit 2; }
[ -b "$device" ] || { echo "target is not a block device: $device" >&2; exit 2; }
[ "$(lsblk -ndo TYPE "$device")" = "disk" ] || { echo "target must be a whole disk: $device" >&2; exit 2; }
[ -f "$squashfs" ] || { echo "runner filesystem not found: $squashfs" >&2; exit 2; }
[[ "$hostname_value" =~ ^[a-z][a-z0-9-]{0,62}$ ]] || { echo "invalid hostname" >&2; exit 2; }
for command in lsblk sfdisk partprobe udevadm blkid cryptsetup mkfs.ext4 mkfs.fat mount umount unsquashfs arch-chroot grub-install grub-mkconfig ssh-keygen; do
  command -v "$command" >/dev/null || { echo "required command missing: $command" >&2; exit 2; }
done

mounted=$(lsblk -nr -o MOUNTPOINT "$device" | sed '/^$/d' || true)
[ -z "$mounted" ] || { echo "refusing mounted target; unmount first: $mounted" >&2; exit 2; }
root_mount=/mnt/mcp-drone-install; mapper=mcp-drone-root; keyfile=$(mktemp); chmod 600 "$keyfile"
cleanup() {
  set +e; sync
  mountpoint -q "$root_mount/boot/efi" && umount "$root_mount/boot/efi"
  mountpoint -q "$root_mount" && umount "$root_mount"
  cryptsetup status "$mapper" >/dev/null 2>&1 && cryptsetup close "$mapper"
  rm -f "$keyfile"
}
trap cleanup EXIT

echo "WARNING: this erases every partition on $device."
read -r -p "Type the exact device path to continue: " typed
[ "$typed" = "$device" ] || { echo "device confirmation did not match" >&2; exit 2; }
read -r -s -p "New LUKS passphrase: " passphrase; echo
read -r -s -p "Repeat LUKS passphrase: " repeat; echo
[ "$passphrase" = "$repeat" ] && [ -n "$passphrase" ] || { echo "passphrases did not match" >&2; exit 2; }
printf '%s' "$passphrase" > "$keyfile"; unset passphrase repeat

case "$device" in /dev/nvme*|/dev/mmcblk*) suffix=p ;; *) suffix="" ;; esac
efi="${device}${suffix}2"; root_partition="${device}${suffix}3"
sfdisk --wipe always "$device" <<EOF
label: gpt
size=1MiB, type=21686148-6449-6E6F-744E-656564454649, name="BIOS boot"
size=512MiB, type=U, name="EFI system"
type=L, name="Encrypted root"
EOF
partprobe "$device" || true; udevadm settle || true
cryptsetup luksFormat --type luks2 --batch-mode --key-file "$keyfile" "$root_partition"
cryptsetup open --key-file "$keyfile" "$root_partition" "$mapper"
mkfs.ext4 -L MCP_DRONE_ROOT "/dev/mapper/$mapper"; mkfs.fat -F 32 -n MCP_DRONE_EFI "$efi"
mkdir -p "$root_mount"; mount "/dev/mapper/$mapper" "$root_mount"; mkdir -p "$root_mount/boot/efi"; mount "$efi" "$root_mount/boot/efi"
unsquashfs -f -d "$root_mount" "$squashfs" >/dev/null
printf '%s\n' "$hostname_value" > "$root_mount/etc/hostname"
printf '/dev/mapper/%s / ext4 defaults 0 1\nUUID=%s /boot/efi vfat umask=0077 0 2\n' "$mapper" "$(blkid -s UUID -o value "$efi")" > "$root_mount/etc/fstab"
printf '/dev/disk/by-uuid/%s %s none luks,discard 0 0\n' "$(blkid -s UUID -o value "$root_partition")" "$mapper" > "$root_mount/etc/crypttab"
root_uuid=$(blkid -s UUID -o value "$root_partition")
cat > "$root_mount/etc/default/grub" <<EOF
GRUB_CMDLINE_LINUX="cryptdevice=UUID=$root_uuid:$mapper root=/dev/mapper/$mapper"
EOF
rm -f "$root_mount/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$root_mount/etc/resolv.conf"

hooks=$(sed -n 's/^HOOKS=(\(.*\))/\1/p' "$root_mount/etc/mkinitcpio.conf" | tr -d '"')
case " $hooks " in
  *" encrypt "*) ;;
  *" filesystems "*) sed -i 's/ filesystems/ encrypt filesystems/' "$root_mount/etc/mkinitcpio.conf" ;;
  *) sed -i "s/^HOOKS=(\(.*\))/HOOKS=(\1 encrypt)/" "$root_mount/etc/mkinitcpio.conf" ;;
esac
arch-chroot "$root_mount" mkinitcpio -P
arch-chroot "$root_mount" grub-install --target=i386-pc "$device"
arch-chroot "$root_mount" grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=MCP-DRONE --recheck
arch-chroot "$root_mount" grub-mkconfig -o /boot/grub/grub.cfg

rm -f "$root_mount/etc/ssh/ssh_host_mcp_drone" "$root_mount/etc/ssh/ssh_host_mcp_drone.pub" "$root_mount/etc/ssh/ssh_host_mcp_drone-cert.pub"
arch-chroot "$root_mount" ssh-keygen -q -t ed25519 -N '' -f /etc/ssh/ssh_host_mcp_drone
chmod 600 "$root_mount/etc/ssh/ssh_host_mcp_drone"; chmod 644 "$root_mount/etc/ssh/ssh_host_mcp_drone.pub"
sync; echo "persistent encrypted installation complete on $device"
