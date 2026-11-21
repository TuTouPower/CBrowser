#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
manifest="${1:-$ROOT/.scratch/images.json}"
lock="$ROOT/config/font_assets.lock.json"
mkdir -p "$ROOT/.scratch" "$(dirname "$manifest")"

font_context="$(mktemp -d "$ROOT/.scratch/build_fonts.XXXXXX")"
trap 'rm -f "$font_context/fonts.tar.zst"; rmdir "$font_context"' EXIT
archive="$font_context/fonts.tar.zst"
expected="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$lock")"
if [ -n "${CBROWSER_FONT_ARCHIVE:-}" ]; then
    cp "$CBROWSER_FONT_ARCHIVE" "$archive"
else
    url="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["url"] or "")' "$lock")"
    if [[ "$url" != https://* ]]; then
        echo "Font bundle URL has not been published. Set CBROWSER_FONT_ARCHIVE to the publisher's locked archive." >&2
        exit 1
    fi
    curl --fail --location --proto '=https' --retry 2 --output "$archive" "$url"
fi
if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$archive" | awk '{print $1}')"
else
    actual="$(shasum -a 256 "$archive" | awk '{print $1}')"
fi
if [ "$actual" != "$expected" ]; then
    echo "Font bundle SHA-256 mismatch: expected $expected, got $actual" >&2
    exit 1
fi
build_id="${CBROWSER_IMAGE_TAG:-$(git rev-parse --short HEAD)}"
images=()
apt_mirror="${CBROWSER_APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"
no_proxy_hosts="${no_proxy:-${NO_PROXY:-}}"
for service in api gateway supervisor browser stream caddy; do
    extra=()
    case "$service" in
        browser|stream|caddy) extra+=(--build-arg "APT_MIRROR=$apt_mirror") ;;
    esac
    if [ "$service" = browser ]; then
        extra+=(--build-context "font_assets=$font_context")
    fi
    if [ -n "$no_proxy_hosts" ]; then
        extra+=(--build-arg "NO_PROXY=$no_proxy_hosts" --build-arg "no_proxy=$no_proxy_hosts")
    fi
    tag="cbrowser-$service:$build_id-${font_context##*.}"
    docker buildx build --load --provenance=false --sbom=false ${extra[@]+"${extra[@]}"} \
        --tag "$tag" --file "config/docker/${service}_runtime/Dockerfile" .
    id="$(docker image inspect --format '{{.Id}}' "$tag")"
    images+=("$service=$id")
done

PYTHONPATH="$ROOT/src/backend" python3 - "$manifest" "${images[@]}" <<'PY'
import json
import sys
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

images = dict(arg.split("=", 1) for arg in sys.argv[2:])
atomic_write_text(Path(sys.argv[1]), json.dumps({"images": images}, indent=2) + "\n")
PY
printf 'Built image manifest: %s\n' "$manifest"
