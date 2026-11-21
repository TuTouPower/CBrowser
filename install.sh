#!/bin/bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
exec bash "$root/scripts/deploy.sh" deploy --images registry "$root/images.json"
