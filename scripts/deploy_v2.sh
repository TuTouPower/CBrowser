#!/bin/bash
# CBrowser release deployment (t027).
#
# Replaces the historical "build twice, overwrite compose.env, restart
# Caddy unconditionally, print the admin password" flow with immutable
# releases:
#
#   deploy    build every runtime image exactly once, tag it with the
#             release id, pin all six image IDs (incl. Caddy) plus the
#             compose/Caddyfile/frontend fingerprints and the database
#             migration version in a release manifest, `up --wait`
#             (never builds), then verify through the Supervisor's single
#             reconcile_all + readiness entry via `docker compose exec`.
#             The current/previous release pointers only move after the
#             readiness verification passes, so a failed deploy never
#             overwrites the previous valid release.
#   rollback  re-deploy the previous (or a named) release after checking
#             it still offers the readiness capability and its migration
#             version is not below the current database version; the
#             same readiness verification runs before success is claimed.
#   status    print the current/previous release ids (never secrets).
#
# Credentials: the admin password is user-provided and must already exist
# at $CBROWSER_SECRETS_DIR/admin_password; missing prerequisites are
# listed together and the script exits before changing anything.  The
# container-internal keys are generated once (0600) when missing and are
# never printed; output only names the password file location.
#
# Instance identity is parameterized (project, prefix, data root,
# secrets dir, HTTPS port) so a second isolated instance can coexist on
# the same Docker daemon (used by t032); a prefix already owned by a
# different running compose project is refused before anything starts.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMMAND="${1:-deploy}"
if [ "$#" -gt 0 ]; then shift; fi

PROJECT="${CBROWSER_COMPOSE_PROJECT:-cbrowser}"
PREFIX="${CBROWSER_PREFIX:-cbrowser}"
HTTPS_PORT="${CBROWSER_HTTPS_PORT:-56661}"
PUBLIC_ORIGIN="${CBROWSER_PUBLIC_ORIGIN:-https://127.0.0.1:$HTTPS_PORT}"
DATA_ROOT="${CBROWSER_DATA_ROOT:-$ROOT/data/v2}"
SECRETS_DIR="${CBROWSER_SECRETS_DIR:-$ROOT/config/deploy/secrets}"
DEPLOY_DIR="${CBROWSER_DEPLOY_DIR:-$ROOT/config/deploy}"
RELEASES_DIR="$DEPLOY_DIR/releases"
CURRENT_FILE="$DEPLOY_DIR/current_release"
PREVIOUS_FILE="$DEPLOY_DIR/previous_release"
CADDY_REF="${CBROWSER_CADDY_REF:-caddy@sha256:70b3180738b46cd88e49b300d790ae448a0aca3f58edef0f000bb57d619a9ab3}"
UP_WAIT_TIMEOUT="${CBROWSER_DEPLOY_DEADLINE_SEC:-600}"
VERIFY_DEADLINE="${CBROWSER_VERIFY_DEADLINE_SEC:-300}"

export CBROWSER_COMPOSE_PROJECT="$PROJECT"
export CBROWSER_PREFIX="$PREFIX"
export CBROWSER_HTTPS_PORT="$HTTPS_PORT"
export CBROWSER_PUBLIC_ORIGIN="$PUBLIC_ORIGIN"
export CBROWSER_DATA_ROOT="$DATA_ROOT"
export CBROWSER_SECRETS_DIR="$SECRETS_DIR"

sha256_of_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

sha256_of_text() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  else
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  fi
}

frontend_fingerprint() {
  # Digest over the sorted (relative path, content sha256) pairs of the
  # built frontend product; identifies exactly what Caddy will serve.
  local dist="$ROOT/src/frontend/dist" listing=""
  local file rel
  while IFS= read -r file; do
    rel="${file#"$dist"/}"
    listing+="$rel $(sha256_of_file "$file")"$'\n'
  done < <(find "$dist" -type f | LC_ALL=C sort)
  sha256_of_text "$listing"
}

migration_head() {
  # The alembic head of the shipped source: the revision that no other
  # revision names as its down_revision.  Fails on branches/multiple heads.
  local versions_dir="$ROOT/src/backend/migrations/versions"
  local revisions="" down_revisions="" file rev down head="" count=0
  for file in "$versions_dir"/*.py; do
    rev="$(sed -n 's/^revision[^=]*= "\(.*\)".*/\1/p' "$file" | head -1)"
    down="$(sed -n 's/^down_revision[^=]*= "\(.*\)".*/\1/p' "$file" | head -1)"
    [ -n "$rev" ] || continue
    revisions+="$rev"$'\n'
    [ -n "$down" ] && down_revisions+="$down"$'\n'
  done
  while IFS= read -r rev; do
    [ -n "$rev" ] || continue
    if ! printf '%s' "$down_revisions" | grep -qx "$rev"; then
      head="$rev"
      count=$((count + 1))
    fi
  done <<< "$revisions"
  if [ "$count" -ne 1 ]; then
    echo "cannot determine a single migration head (found $count)" >&2
    return 1
  fi
  printf '%s' "$head"
}

atomic_write() {
  # atomic_write <path> ; content on stdin
  local path="$1" tmp
  tmp="$(mktemp "$path.tmp.XXXXXX")"
  cat > "$tmp"
  mv "$tmp" "$path"
}

read_pointer() {
  local file="$1"
  if [ -s "$file" ]; then
    tr -d '[:space:]' < "$file"
  fi
}

manifest_field() {
  # manifest_field <manifest.json> <field> : top-level string field
  sed -n "s/.*\"$2\": \"\([^\"]*\)\".*/\1/p" "$1" | head -1
}

compose_with() {
  local env_file="$1"
  shift
  docker compose --env-file "$env_file" -f compose.yaml "$@"
}

probe_exec() {
  # probe_exec <env_file> <probe args...> : run the readiness probe inside
  # the Supervisor container; prints its redacted JSON either way and
  # returns the probe exit code.
  local env_file="$1"
  shift
  local out rc
  set +e
  out="$(compose_with "$env_file" exec -T supervisor python3 - "$@" \
    < "$ROOT/scripts/supervisor_readiness_probe.py")"
  rc=$?
  set -e
  if [ -n "$out" ]; then
    printf '%s\n' "$out"
  fi
  return "$rc"
}

verify_readiness() {
  # verify_readiness <env_file> : 0 when every desired=running Profile is
  # converged per the Supervisor readiness report.
  probe_exec "$1" verify "$VERIFY_DEADLINE"
}

record_applied_migration() {
  # The API migrates the database at startup, so any release whose stack
  # was brought up may have raised the live database version even when
  # the deploy afterwards failed verification and the release pointers
  # never moved.  Record the highest migration version actually applied
  # (monotonic); the rollback gate uses it as the database floor.
  local release_id="$1" migration applied
  migration="$(manifest_field "$RELEASES_DIR/$release_id.json" migration_version)"
  [ -n "$migration" ] || return 0
  applied="$(read_pointer "$DEPLOY_DIR/applied_migration_version")"
  if [ -z "$applied" ] || [[ "$applied" < "$migration" ]]; then
    printf '%s\n' "$migration" | atomic_write "$DEPLOY_DIR/applied_migration_version"
  fi
}

deploy_up_and_verify() {
  # deploy_up_and_verify <release_id> : up --wait + readiness gate.
  local release_id="$1"
  local env_file="$RELEASES_DIR/$release_id.env"
  if ! compose_with "$env_file" up -d --no-build --wait --wait-timeout "$UP_WAIT_TIMEOUT"; then
    echo "compose up did not reach a healthy state within ${UP_WAIT_TIMEOUT}s (release $release_id)" >&2
    record_applied_migration "$release_id"
    # Read-only per-Profile diagnostics for the failure report (single
    # readiness snapshot, no new reconcile, no polling); the deploy is a
    # failure regardless of what the probe returns here.
    probe_exec "$env_file" report || true
    return 1
  fi
  record_applied_migration "$release_id"
  if ! verify_readiness "$env_file"; then
    echo "readiness verification failed for release $release_id; previous release remains current" >&2
    return 1
  fi
}

activate_release() {
  # activate_release <release_id> : move current/previous pointers after
  # a verified deploy or rollback.  Atomic, and never touches data.
  local release_id="$1" current
  current="$(read_pointer "$CURRENT_FILE")"
  if [ -n "$current" ] && [ "$current" != "$release_id" ]; then
    printf '%s\n' "$current" | atomic_write "$PREVIOUS_FILE"
  fi
  printf '%s\n' "$release_id" | atomic_write "$CURRENT_FILE"
}

check_prerequisites() {
  local missing=()
  command -v docker >/dev/null 2>&1 || missing+=("docker CLI not on PATH")
  if command -v docker >/dev/null 2>&1; then
    docker compose version >/dev/null 2>&1 || missing+=("docker compose plugin unavailable")
  fi
  [ -s "$SECRETS_DIR/admin_password" ] || \
    missing+=("user-provided admin password: $SECRETS_DIR/admin_password (create it with mode 0600; it is never generated)")
  [ -f "$ROOT/src/frontend/dist/index.html" ] || \
    missing+=("frontend product: src/frontend/dist/index.html (run: npm ci --prefix src/frontend && npm run build --prefix src/frontend)")
  [ -f "$ROOT/config/deploy/caddy/Caddyfile" ] || \
    missing+=("Caddyfile: config/deploy/caddy/Caddyfile")
  local name
  for name in browser_runtime stream_runtime supervisor_runtime gateway_runtime api_runtime; do
    [ -f "$ROOT/config/docker/$name/Dockerfile" ] || missing+=("Dockerfile: config/docker/$name/Dockerfile")
    [ -f "$ROOT/config/docker/$name/Dockerfile.dockerignore" ] || missing+=("build-context rules: config/docker/$name/Dockerfile.dockerignore")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "Missing deploy prerequisites:" >&2
    printf ' - %s\n' "${missing[@]}" >&2
    exit 1
  fi
}

ensure_internal_secrets() {
  # Container-internal keys: generated once when missing, 0600, and never
  # printed.  The admin password is NOT handled here (user-provided).
  mkdir -p "$SECRETS_DIR"
  local name file
  for name in supervisor_key agent_key gateway_key gateway_api_key; do
    file="$SECRETS_DIR/$name"
    if [ ! -s "$file" ]; then
      ( umask 077; openssl rand -hex 32 > "$file" )
    fi
    chmod 600 "$file"
  done
  chmod 600 "$SECRETS_DIR/admin_password"
}

check_prefix_conflict() {
  # Refuse when another compose project already owns our resource
  # prefix: its Supervisor would treat this instance's Profiles as
  # orphans (and vice versa).  Scan ALL containers (running or stopped)
  # and attribute by container name and prefix label, not just by the
  # one labelled fixed service: an instance whose Gateway has exited
  # still owns its prefix through its Supervisor and Profile containers.
  local rows name project row_prefix
  rows="$(docker ps -a --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.cbrowser.prefix"}}')"
  while IFS=$'\t' read -r name project row_prefix; do
    [ -n "$name" ] || continue
    case "$name" in
      "$PREFIX"-*) ;;
      *) [ "$row_prefix" = "$PREFIX" ] || continue ;;
    esac
    if [ -n "$project" ] && [ "$project" != "$PROJECT" ]; then
      echo "Refusing to start: resource prefix '$PREFIX' is already used by instance (compose project '$project', container '$name')." >&2
      echo "Choose a different CBROWSER_PREFIX/CBROWSER_COMPOSE_PROJECT for this instance." >&2
      exit 1
    fi
  done <<< "$rows"
}

load_release_identity() {
  # load_release_identity <env_file> : adopt the instance identity
  # recorded in a release env (project, prefix, port, origin, data root,
  # secrets dir).  Compose interpolation prefers the shell environment
  # over --env-file values, so a rollback must run with the TARGET
  # release's identity, never with whatever the caller's shell exports.
  local env_file="$1" line key value
  while IFS= read -r line; do
    case "$line" in
      CBROWSER_COMPOSE_PROJECT=*|CBROWSER_PREFIX=*|CBROWSER_HTTPS_PORT=*|\
      CBROWSER_PUBLIC_ORIGIN=*|CBROWSER_DATA_ROOT=*|CBROWSER_SECRETS_DIR=*)
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
        ;;
    esac
  done < "$env_file"
  PROJECT="$CBROWSER_COMPOSE_PROJECT"
  PREFIX="$CBROWSER_PREFIX"
  HTTPS_PORT="$CBROWSER_HTTPS_PORT"
  PUBLIC_ORIGIN="$CBROWSER_PUBLIC_ORIGIN"
  DATA_ROOT="$CBROWSER_DATA_ROOT"
  SECRETS_DIR="$CBROWSER_SECRETS_DIR"
}

build_and_record_release() {
  # Builds each image once, writes <id>.env + <id>.json under releases/.
  local release_id="$1"
  local tag_api="cbrowser-api:$release_id" tag_gateway="cbrowser-gateway:$release_id"
  local tag_supervisor="cbrowser-supervisor:$release_id" tag_browser="cbrowser-browser:$release_id"
  local tag_stream="cbrowser-stream:$release_id"

  # Attestation manifests embed per-invocation build metadata, so an
  # otherwise identical rebuild would get a different image ID and force
  # compose to recreate healthy services. Disable them: the release
  # manifest pins the rootfs/config digest, which is what reproducibility
  # and rollback identity depend on (t032 AC-001/AC-010).
  docker build --provenance=false --sbom=false -t "$tag_browser" -f config/docker/browser_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_stream" -f config/docker/stream_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_supervisor" -f config/docker/supervisor_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_gateway" -f config/docker/gateway_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_api" -f config/docker/api_runtime/Dockerfile .
  if ! docker image inspect "$CADDY_REF" >/dev/null 2>&1; then
    docker pull "$CADDY_REF"
  fi

  local api_id gateway_id supervisor_id browser_id stream_id caddy_id
  api_id="$(docker image inspect --format '{{.Id}}' "$tag_api")"
  gateway_id="$(docker image inspect --format '{{.Id}}' "$tag_gateway")"
  supervisor_id="$(docker image inspect --format '{{.Id}}' "$tag_supervisor")"
  browser_id="$(docker image inspect --format '{{.Id}}' "$tag_browser")"
  stream_id="$(docker image inspect --format '{{.Id}}' "$tag_stream")"
  caddy_id="$(docker image inspect --format '{{.Id}}' "$CADDY_REF")"

  local compose_sha caddyfile_sha frontend_sha migration
  compose_sha="$(sha256_of_file "$ROOT/compose.yaml")"
  caddyfile_sha="$(sha256_of_file "$ROOT/config/deploy/caddy/Caddyfile")"
  frontend_sha="$(frontend_fingerprint)"
  migration="$(migration_head)"

  mkdir -p "$RELEASES_DIR"
  cat <<ENV | atomic_write "$RELEASES_DIR/$release_id.env"
CBROWSER_COMPOSE_PROJECT=$PROJECT
CBROWSER_PREFIX=$PREFIX
CBROWSER_HTTPS_PORT=$HTTPS_PORT
CBROWSER_PUBLIC_ORIGIN=$PUBLIC_ORIGIN
CBROWSER_DATA_ROOT=$DATA_ROOT
CBROWSER_SECRETS_DIR=$SECRETS_DIR
CBROWSER_API_IMAGE=$api_id
CBROWSER_GATEWAY_IMAGE=$gateway_id
CBROWSER_SUPERVISOR_IMAGE=$supervisor_id
CBROWSER_BROWSER_IMAGE=$browser_id
CBROWSER_STREAM_IMAGE=$stream_id
CBROWSER_CADDY_IMAGE=$caddy_id
CBROWSER_CADDYFILE_SHA256=$caddyfile_sha
CBROWSER_FRONTEND_SHA256=$frontend_sha
ENV

  local created_at
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat <<JSON | atomic_write "$RELEASES_DIR/$release_id.json"
{
  "release_id": "$release_id",
  "created_at": "$created_at",
  "images": {
    "api": "$api_id",
    "gateway": "$gateway_id",
    "supervisor": "$supervisor_id",
    "browser": "$browser_id",
    "stream": "$stream_id",
    "caddy": "$caddy_id"
  },
  "compose_sha256": "$compose_sha",
  "caddyfile_sha256": "$caddyfile_sha",
  "frontend_sha256": "$frontend_sha",
  "migration_version": "$migration",
  "capabilities": {"readiness": true, "reconcile_all": true},
  "instance": {"project": "$PROJECT", "prefix": "$PREFIX", "https_port": $HTTPS_PORT}
}
JSON
}

cmd_deploy() {
  check_prerequisites
  ensure_internal_secrets
  mkdir -p "$DATA_ROOT"/{profiles,runtime,runtime-events,artifacts,spool,control,engine-cache/geoip}
  check_prefix_conflict

  local release_id="${CBROWSER_RELEASE_ID:-}"
  if [ -z "$release_id" ]; then
    local short_sha
    short_sha="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
    release_id="$(date +%Y%m%d%H%M%S)-$short_sha"
  fi
  if [ -e "$RELEASES_DIR/$release_id.json" ]; then
    echo "Refusing to overwrite existing release '$release_id' (releases are immutable); pick a new CBROWSER_RELEASE_ID." >&2
    exit 1
  fi

  build_and_record_release "$release_id"
  deploy_up_and_verify "$release_id"
  activate_release "$release_id"

  echo "Release $release_id deployed and readiness-verified."
  echo "  URL: https://127.0.0.1:$HTTPS_PORT"
  echo "  Manifest: $RELEASES_DIR/$release_id.json"
  echo "  Admin password: stored at $SECRETS_DIR/admin_password (value never printed)"
}

cmd_rollback() {
  local target="${1:-}"
  if [ -z "$target" ]; then
    target="$(read_pointer "$PREVIOUS_FILE")"
  fi
  if [ -z "$target" ]; then
    echo "No rollback target: no previous release recorded." >&2
    exit 1
  fi
  local target_manifest="$RELEASES_DIR/$target.json" target_env="$RELEASES_DIR/$target.env"
  if [ ! -f "$target_manifest" ] || [ ! -f "$target_env" ]; then
    echo "Rollback target release '$target' is incomplete (manifest/env missing)." >&2
    exit 1
  fi
  # From here on, everything (conflict check, compose interpolation,
  # data root, secrets) uses the target release's recorded identity.
  load_release_identity "$target_env"
  local current current_manifest
  current="$(read_pointer "$CURRENT_FILE")"
  if [ -z "$current" ] || [ ! -f "$RELEASES_DIR/$current.json" ]; then
    echo "No current release recorded; nothing to roll back from." >&2
    exit 1
  fi
  if [ "$target" = "$current" ]; then
    echo "Rollback target '$target' is already the current release." >&2
    exit 1
  fi
  current_manifest="$RELEASES_DIR/$current.json"

  # Refuse BEFORE changing anything when the target cannot be verified
  # by the current acceptance contract, or would run migrations older
  # than the live database (no downgrade migrations exist).
  if ! grep -q '"readiness": true' "$target_manifest"; then
    echo "Refusing rollback to '$target': release does not offer the readiness capability required for acceptance." >&2
    exit 1
  fi
  local target_migration current_migration db_floor applied_migration
  target_migration="$(manifest_field "$target_manifest" migration_version)"
  current_migration="$(manifest_field "$current_manifest" migration_version)"
  if [ -z "$target_migration" ] || [ -z "$current_migration" ]; then
    echo "Refusing rollback: migration version missing from a release manifest." >&2
    exit 1
  fi
  # The database floor is the highest migration actually applied, which
  # can exceed the current release's manifest when a later deploy
  # migrated the database and then failed verification (the API migrates
  # at startup, before any pointer moves).
  db_floor="$current_migration"
  applied_migration="$(read_pointer "$DEPLOY_DIR/applied_migration_version")"
  if [ -n "$applied_migration" ] && [[ "$db_floor" < "$applied_migration" ]]; then
    db_floor="$applied_migration"
  fi
  if [[ "$target_migration" < "$db_floor" ]]; then
    echo "Refusing rollback to '$target': its migration version ($target_migration) is below the live database version ($db_floor)." >&2
    exit 1
  fi

  check_prefix_conflict
  deploy_up_and_verify "$target"
  activate_release "$target"
  echo "Rolled back to release $target and readiness-verified."
  echo "  Manifest: $target_manifest"
}

cmd_status() {
  local current previous
  current="$(read_pointer "$CURRENT_FILE")"
  previous="$(read_pointer "$PREVIOUS_FILE")"
  echo "current: ${current:-<none>}"
  echo "previous: ${previous:-<none>}"
  if [ -n "$current" ] && [ -f "$RELEASES_DIR/$current.json" ]; then
    echo "manifest: $RELEASES_DIR/$current.json"
  fi
}

case "$COMMAND" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback "$@" ;;
  status) cmd_status ;;
  *) echo "usage: $0 [deploy|rollback [release_id]|status]" >&2; exit 2 ;;
esac
