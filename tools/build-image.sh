#!/usr/bin/env bash
set -euo pipefail

project_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
profile_dir="${MCP_DRONE_PROFILE:-$project_dir/runner/profile}"
output_dir="${1:-$project_dir/out}"
work_dir="${MCP_DRONE_WORK:-$project_dir/work}"
staging_dir=$(mktemp -d)
trap 'rm -rf "$staging_dir"' EXIT
staged_profile="$staging_dir/profile"
cp -a "$profile_dir" "$staged_profile"
mkdir -p "$staged_profile/airootfs/opt/mcp-drone-os"
cp -a "$project_dir/src/mcp_drone_os" "$staged_profile/airootfs/opt/mcp-drone-os/"
install -D -m 0755 "$project_dir/tools/install-persistent.sh" \
  "$staged_profile/airootfs/usr/local/bin/mcp-drone-install"
if [ -n "${MCP_DRONE_MANIFEST:-}" ]; then
  test -f "$MCP_DRONE_MANIFEST" || { echo "manifest not found: $MCP_DRONE_MANIFEST" >&2; exit 2; }
  test -n "${MCP_DRONE_ENROLLMENT:-}" || { echo "MCP_DRONE_ENROLLMENT is required with MCP_DRONE_MANIFEST" >&2; exit 2; }
  test -f "$MCP_DRONE_ENROLLMENT" || { echo "enrollment config not found: $MCP_DRONE_ENROLLMENT" >&2; exit 2; }
  mkdir -p "$staged_profile/airootfs/etc/mcp-drone"
  cp "$MCP_DRONE_MANIFEST" "$staged_profile/airootfs/etc/mcp-drone/manifest.json"
  cp "$MCP_DRONE_ENROLLMENT" "$staged_profile/airootfs/etc/mcp-drone/enrollment.json"
fi

if ! command -v mkarchiso >/dev/null 2>&1; then
  echo "mkarchiso is required; install the Arch 'archiso' package or run this script inside an Arch build container" >&2
  exit 2
fi
test -f "$staged_profile/profiledef.sh" || { echo "missing profile: $staged_profile/profiledef.sh" >&2; exit 2; }
mkdir -p "$output_dir"
mkarchiso -v -r -w "$work_dir" -o "$output_dir" "$staged_profile"
image="$output_dir/mcp-drone-os-0.1.0-x86_64.iso"
sha256sum "$image" > "$image.sha256"
echo "sha256: $(cut -d' ' -f1 "$image.sha256")"
