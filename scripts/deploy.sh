#!/bin/bash
# CBrowser release deployment (t027, t051).
#
# Replaces the historical "build twice, overwrite compose.env, restart
# Caddy unconditionally, print the admin password" flow with immutable
# releases:
#
#   deploy    build the API image first, then inspect the live database
#             stamp inside a throwaway API container (named volume, never
#             the host file), refuse a retired-generation stamp, warn about
#             a legacy host database left behind, warn about a missing or
#             invalid font directory, back the live database up into
#             config/deploy/backups, build the remaining images exactly
#             once, tag them with the release id, pin all six image IDs
#             (incl. Caddy) plus the compose/Caddyfile/frontend
#             fingerprints, the database migration version and the backup
#             path in a release manifest, `up --wait` (never builds), then
#             verify through the Supervisor's single reconcile_all +
#             readiness entry via `docker compose exec`.  The single JSON
#             release pointer only moves after the readiness verification
#             passes, so a failed deploy never overwrites the previous
#             valid release.
#   rollback  re-deploy the previous (or a named) release after checking
#             it still offers the readiness capability, its migration
#             head belongs to the current Alembic revision chain, and its
#             head equals the live database stamp (no downgrade: a stale
#             same-generation head and a retired-generation release are
#             both refused, including old t042 releases that would need the
#             deleted ALLOWED_ORIGINS — refuse, no compat); its compose
#             file fingerprint must still match the working tree (no mixed
#             old-images/new-compose); the same readiness verification
#             runs before success is claimed.
#   restore   stop the stack and copy a backup file back into the database
#             volume (stale -wal/-shm removed first); the user re-deploys
#             afterwards.  Never deletes the backup.
#   env-backup [point-dir]
#             capture a full environment restore point (database volume
#             plus every Profile user data directory, one quiescent set
#             with a verifiable manifest) via scripts/restore_point.py;
#             refuses while any Profile has an actual writer.  Credential
#             files are prerequisites listed by name only, never copied.
#   env-restore <point-dir>
#             stop the stack and restore an environment restore point as
#             one validated set (staging validation, journaled switch,
#             pre-restore set retained); the user re-deploys afterwards.
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
# the same Docker daemon (used by t032).  The deployment instance id is
# derived deterministically from (prefix, data root) and written to the
# com.cbrowser.instance-id label on every control-plane service,
# sandbox, helper and network: it is the sole ownership test for the
# prefix-conflict check, replacing the old <prefix>-profiles project-name
# exemption.  Each instance also derives a /16 media subnet pool from the
# same identity; a foreign pool overlapping ours refuses the deploy.
# A prefix already owned by a different deployment is refused before
# anything starts; a malformed prefix is refused even earlier.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMMAND="${1:-deploy}"
if [ "$#" -gt 0 ]; then shift; fi

PROJECT="${CBROWSER_COMPOSE_PROJECT:-cbrowser}"
PREFIX="${CBROWSER_PREFIX:-cbrowser}"

NET_CONFIG_PY="${CBROWSER_PYTHON:-}"
if [ -z "$NET_CONFIG_PY" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then
    NET_CONFIG_PY="$ROOT/.venv/bin/python"
  else
    NET_CONFIG_PY="python3"
  fi
fi

# t054: the default HTTPS port is the single constant in
# cbrowser.network_config (DEFAULT_HTTPS_PORT) — no literal copy here.
DEFAULT_HTTPS_PORT="$(PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
  "$NET_CONFIG_PY" -c 'from cbrowser.network_config import DEFAULT_HTTPS_PORT; print(DEFAULT_HTTPS_PORT)')"
HTTPS_PORT="${CBROWSER_HTTPS_PORT:-$DEFAULT_HTTPS_PORT}"
DATA_ROOT="${CBROWSER_DATA_ROOT:-$ROOT/data/instance}"
SECRETS_DIR="${CBROWSER_SECRETS_DIR:-$ROOT/config/deploy/secrets}"
DEPLOY_DIR="${CBROWSER_DEPLOY_DIR:-$ROOT/config/deploy}"
RELEASES_DIR="$DEPLOY_DIR/releases"
BACKUP_DIR="$DEPLOY_DIR/backups"
POINTER_FILE="$DEPLOY_DIR/release_pointer.json"
FONTS_DIR="${CBROWSER_FONTS_DIR:-$ROOT/data/fonts}"
CADDY_REF="${CBROWSER_CADDY_REF:-caddy@sha256:70b3180738b46cd88e49b300d790ae448a0aca3f58edef0f000bb57d619a9ab3}"
UP_WAIT_TIMEOUT="${CBROWSER_DEPLOY_DEADLINE_SEC:-600}"
VERIFY_DEADLINE="${CBROWSER_VERIFY_DEADLINE_SEC:-300}"

# Filled by check_database_schema_generation / backup_database.
CURRENT_DB_STAMP=""
DATABASE_BACKUP_PATH=""

# The resource prefix is a Docker label value and a compose project
# fragment: validate it before any Docker operation (A22).
if [[ ! "$PREFIX" =~ ^[a-z0-9][a-z0-9_]*$ ]]; then
  echo "Refusing to start: CBROWSER_PREFIX '$PREFIX' is invalid (must match ^[a-z0-9][a-z0-9_]*\$)." >&2
  exit 1
fi

# t035: the single baseline Alembic revision.  Membership in the shipped
# revision chain is decided by the chain itself, not by equality with this
# baseline: after the first deploy the live database is stamped at the
# chain head, and only a stamp outside the shipped chain belongs to the
# retired 0001-0009 schema generation and must be rebuilt, never upgraded
# in place.  Kept in sync with the API-side constant in
# cbrowser/adapters/database/migrations.py.
BASELINE_REVISION="b7e1c9d4a2f3"
REBUILD_GUIDANCE="This database was created by a retired CBrowser schema generation (0001-0009). Rebuild the data directory from scratch: stop the stack, move the old data root aside, then start with an empty data directory so the baseline schema is created fresh. No in-place data migration is provided (project decision: no formal users before t035)."

export CBROWSER_COMPOSE_PROJECT="$PROJECT"
export CBROWSER_PREFIX="$PREFIX"
export CBROWSER_HTTPS_PORT="$HTTPS_PORT"
export CBROWSER_DATA_ROOT="$DATA_ROOT"
export CBROWSER_SECRETS_DIR="$SECRETS_DIR"
export CBROWSER_FONTS_DIR="$FONTS_DIR"

db_volume_name() {
  # The named volume holding the control-plane database; must match the
  # `db` volume name in compose.yaml.
  printf '%s-db' "$PREFIX"
}

derive_instance_identity() {
  # A59: the deployment instance id is deterministic in (prefix,
  # data root) — stable across releases and checkouts, so a redeployed
  # Supervisor still claims its running sandboxes; distinct per
  # (prefix, data root).  The media subnet pool derives from the same
  # digest: pool index = digest mod 64, pool = 10.(192+index).0.0/16.
  # The edge subnet derives from the same digest too (t054): index =
  # digest mod 14, subnet = 172.(18+index).0.0/16 — a fixed per-instance
  # /16 that never collides with Docker's default 172.17.0.0/16 bridge,
  # so two instances can coexist on one daemon (t032 dual-instance).
  # The material string is the contract: tests and the Supervisor side
  # must reproduce it byte for byte.
  local out
  out="$(python3 - "$PREFIX" "$DATA_ROOT" <<'PY'
import hashlib
import sys

prefix, data_root = sys.argv[1], sys.argv[2]
material = ("cbrowser-instance-v1\0" + prefix + "\0" + data_root).encode()
digest = hashlib.sha256(material).hexdigest()
print(digest[:32])
print("10.%d.0.0/16" % (192 + int(digest, 16) % 64))
print("172.%d.0.0/16" % (18 + int(digest, 16) % 14))
PY
)"
  CBROWSER_INSTANCE_ID="$(printf '%s' "$out" | sed -n '1p')"
  CBROWSER_MEDIA_SUBNET_POOL="$(printf '%s' "$out" | sed -n '2p')"
  # t054 R1 f001: an explicitly set CBROWSER_EDGE_SUBNET wins over the
  # derived value — the conflict hint tells the operator to set one, so
  # the derivation must not discard it. The explicit value still goes
  # through check_edge_subnet_conflict below (an invalid CIDR is refused
  # there, exit 2), and is recorded in the release env/manifest like the
  # derived value, so rollback keeps using it.
  if [ -z "${CBROWSER_EDGE_SUBNET:-}" ]; then
    CBROWSER_EDGE_SUBNET="$(printf '%s' "$out" | sed -n '3p')"
  fi
  export CBROWSER_INSTANCE_ID CBROWSER_MEDIA_SUBNET_POOL CBROWSER_EDGE_SUBNET
}

pools_overlap() {
  # pools_overlap <cidr-a> <cidr-b> : 0 when the two pools overlap.
  python3 - "$1" "$2" <<'PY'
import ipaddress
import sys

try:
    a = ipaddress.ip_network(sys.argv[1])
    b = ipaddress.ip_network(sys.argv[2])
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if a.overlaps(b) else 1)
PY
}

check_edge_subnet_conflict() {
  # t054: refuse before anything starts when the derived edge subnet
  # overlaps an existing Docker network subnet or a host interface
  # address. Docker would refuse the second bridge network at compose-up
  # time; refusing here names the fix up front.
  # t054 R2 test f005: exclude this instance's own edge network
  # ("${PREFIX}-edge") when its subnet equals the candidate — after the
  # first deploy that network already exists with exactly this subnet,
  # and a redeploy or rollback must not be refused by its own network.
  # The exclusion is name AND subnet (see check_edge_subnet.py): a
  # same-name network with a different subnet is stale and is still
  # refused, with its own remedy on stderr.
  local detail
  if detail="$(python3 "$ROOT/scripts/check_edge_subnet.py" "$CBROWSER_EDGE_SUBNET" --exclude-network "$PREFIX-edge" 2>&1)"; then
    return 0
  fi
  echo "Refusing to start: $detail" >&2
  echo "Choose a different CBROWSER_PREFIX/CBROWSER_DATA_ROOT for this instance (the edge subnet derives from the instance identity), or set an explicit CBROWSER_EDGE_SUBNET." >&2
  exit 1
}

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

current_revision_chain() {
  # The Alembic revision ids shipped in this source tree: the current
  # schema generation's revision chain.  A release whose migration head
  # is absent here was built from the retired 0001-0009 chain (t035
  # AC-002) and is not a valid rollback target.
  local versions_dir="$ROOT/src/backend/migrations/versions" file rev
  for file in "$versions_dir"/*.py; do
    [ -f "$file" ] || continue
    rev="$(sed -n 's/^revision[^=]*= "\(.*\)".*/\1/p' "$file" | head -1)"
    [ -n "$rev" ] && printf '%s\n' "$rev"
  done
  return 0
}

current_db_stamp() {
  # current_db_stamp <api-image> : print the live database's Alembic
  # stamp (empty when absent/unclaimed).  The database lives in the named
  # volume; it is read inside a throwaway API-image container via
  # scripts/db_inspect.py (read-only mount), so the host never opens the
  # database file.  Fails closed when the volume holds a database that
  # cannot be read (A44): an unreadable database is refused, never
  # silently treated as "no database".
  local api_image="$1" db_volume stamp rc
  db_volume="$(db_volume_name)"
  set +e
  stamp="$(docker run --rm \
    -v "$db_volume:/db:ro" \
    -v "$ROOT/scripts:/scripts:ro" \
    "$api_image" python3 /scripts/db_inspect.py stamp --db /db/cbrowser.db)"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    echo "Failed to inspect database schema generation in volume $db_volume (db_inspect exit $rc)." >&2
    return 1
  fi
  # Command substitution strips trailing newlines; an empty stamp means
  # "no migration generation claimed" and is left to API startup.
  printf '%s' "$stamp" | tr -d '[:space:]'
  return 0
}

check_database_schema_generation() {
  # AC-002 (t035, P1-8): a database stamped with a retired 0001-0009
  # revision must NOT be deployed or rolled back against.  Inspect it
  # read-only inside the API image (current_db_stamp) and fail closed,
  # printing REBUILD_GUIDANCE, before any container is started or pointer
  # moved.  The API image is built first for exactly this reason:
  # building an image changes no data.  Membership is decided by the
  # Alembic revision chain shipped in this source tree
  # (current_revision_chain), not by a single BASELINE_REVISION
  # equality: after the first deploy the live database is stamped at the
  # chain head (0002/0003/0004...), and a baseline-only comparison would
  # mis-kill every second deploy and rollback.  An absent database, one
  # without an alembic_version table and without business tables, or one
  # stamped with any shipped chain member is left for the API to
  # create/upgrade on startup.  A database that already holds business
  # tables but no usable stamp is refused by the API-side guard instead
  # (LegacySchemaError with rebuild guidance, t056 A29).  The database
  # file is never opened for writing here.  Cross-generation
  # rollback (live DB stamped outside the shipped chain, or rollback
  # target head outside the shipped chain) is refused here and at the
  # target check below: rebuild the data directory from scratch, no
  # in-place cross-generation migration and no ALLOWED_ORIGINS compat.
  # Sets CURRENT_DB_STAMP for the backup / legacy-database steps.
  local api_image="$1" current chain
  if ! current="$(current_db_stamp "$api_image")"; then
    return 1
  fi
  CURRENT_DB_STAMP="$current"
  # An empty stamp means "no migration generation claimed" and is left to
  # API startup.
  [ -z "$current" ] && return 0
  chain="$(current_revision_chain)"
  if ! grep -qxF "$current" <<< "$chain"; then
    echo "Refusing to deploy: database in volume $(db_volume_name) is stamped with revision '$current', which is not in the current Alembic revision chain." >&2
    echo "$REBUILD_GUIDANCE" >&2
    return 1
  fi
}

check_legacy_host_database() {
  # AC-004: when the volume holds no database but a database file exists
  # at a legacy host location, say so and how to use it — and never
  # delete, move or overwrite it.  The deploy continues.
  [ -n "$CURRENT_DB_STAMP" ] && return 0
  local legacy seen=""
  for legacy in "$ROOT/data/v2/cbrowser.db" "$DATA_ROOT/cbrowser.db"; do
    case " $seen " in *" $legacy "*) continue ;; esac
    seen+=" $legacy"
    if [ -f "$legacy" ]; then
      echo "NOTE: a database file from a previous data layout exists at $legacy, but the database volume is empty."
      echo "  It was NOT moved or deleted. To use it, run: $0 restore $legacy (after this deploy), or move it aside."
    fi
  done
}

check_font_sets_preflight() {
  # AC-009/AC-010: warn (never block) when the fonts directory is missing
  # or holds no valid set; the deploy continues on the built-in fonts.
  python3 "$ROOT/scripts/check_font_sets.py" --fonts-dir "$FONTS_DIR" || true
}

check_engine_artifact_preflight() {
  local out
  if ! out="$(PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
      "$NET_CONFIG_PY" -m cbrowser.engine_artifacts describe --shell)"; then
    echo "Refusing to start: pinned engine artifact verification failed." >&2
    exit 1
  fi
  eval "$out"
  CBROWSER_ENGINE_PLATFORM="${CBROWSER_ENGINE_PLATFORM:-}"
  CBROWSER_ENGINE_BUILD="${CBROWSER_ENGINE_BUILD:-}"
  CBROWSER_ENGINE_VERSION="${CBROWSER_ENGINE_VERSION:-}"
  CBROWSER_ENGINE_ARCHIVE_SHA256="${CBROWSER_ENGINE_ARCHIVE_SHA256:-}"
  CBROWSER_ENGINE_BINARY_SHA256="${CBROWSER_ENGINE_BINARY_SHA256:-}"
  CBROWSER_ENGINE_INTEGRITY_MECHANISM="${CBROWSER_ENGINE_INTEGRITY_MECHANISM:-}"
  CBROWSER_ENGINE_TRUST_SOURCE="${CBROWSER_ENGINE_TRUST_SOURCE:-}"
  CBROWSER_CLOAKBROWSER_PACKAGE="${CBROWSER_CLOAKBROWSER_PACKAGE:-}"
  CLOAKBROWSER_AUTO_UPDATE="${CLOAKBROWSER_AUTO_UPDATE:-false}"
  if [ -d "$DATA_ROOT/engine-cache" ]; then
    if ! PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
        "$NET_CONFIG_PY" -m cbrowser.engine_artifacts verify-cache \
        --cache-dir "$DATA_ROOT/engine-cache" --allow-empty --no-version-probe >/dev/null; then
      echo "Refusing to start: engine cache verification failed at $DATA_ROOT/engine-cache." >&2
      exit 1
    fi
  fi
  export CBROWSER_ENGINE_PLATFORM CBROWSER_ENGINE_BUILD CBROWSER_ENGINE_VERSION \
    CBROWSER_ENGINE_ARCHIVE_SHA256 CBROWSER_ENGINE_BINARY_SHA256 \
    CBROWSER_ENGINE_INTEGRITY_MECHANISM CBROWSER_ENGINE_TRUST_SOURCE \
    CBROWSER_CLOAKBROWSER_PACKAGE CLOAKBROWSER_AUTO_UPDATE
}

backup_database() {
  # AC-003: back up the live database (SQLite online-backup API, read-only
  # source) before `up` moves anything.  The backup path is recorded in
  # the release manifest (DATABASE_BACKUP_PATH).  A fresh install (no live
  # database) skips the backup.  A failed backup refuses the deploy.
  local api_image="$1"
  if [ -z "$CURRENT_DB_STAMP" ]; then
    echo "No live database; skipping backup."
    DATABASE_BACKUP_PATH=""
    return 0
  fi
  mkdir -p "$BACKUP_DIR"
  local stamp backup_file
  stamp="$(date +%Y%m%d%H%M%S)"
  backup_file="$BACKUP_DIR/cbrowser-$stamp.db"
  if ! docker run --rm \
    -v "$(db_volume_name):/db" \
    -v "$BACKUP_DIR:/backup" \
    -v "$ROOT/scripts:/scripts:ro" \
    "$api_image" python3 /scripts/db_backup.py \
    --db /db/cbrowser.db --out "/backup/cbrowser-$stamp.db"; then
    echo "Failed to back up the live database; refusing to deploy." >&2
    return 1
  fi
  DATABASE_BACKUP_PATH="$backup_file"
  echo "Database backed up to $backup_file."
}

atomic_write() {
  # atomic_write <path> ; content on stdin
  # Crash-consistent via cbrowser.shared.atomic_write.atomic_write_text
  # (A43): the temp file is fsynced, renamed, and its parent directory is
  # fsynced, so a crash leaves either the old content or the new one.
  PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
    "$NET_CONFIG_PY" -c '
import sys
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

atomic_write_text(Path(sys.argv[1]), sys.stdin.read())
' "$1"
}

network_config() {
  # t054: the only operation is `render` (deterministic Caddyfile for the
  # deploy port). A render failure refuses the deploy with the CLI's exit
  # code; there is no applied-state file to be missing or corrupt anymore.
  local op="${1:-}" read_output rc
  if read_output="$(PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
      "$NET_CONFIG_PY" -m cbrowser.network_config_cli "$@")"; then
    printf '%s\n' "$read_output"
  else
    rc=$?
    echo "Refusing to deploy: network_config $op failed (exit $rc)." >&2
    printf 'exit %d\n' "$rc"
  fi
}

read_pointer() {
  # read_pointer <pointer.json> [field=current] : the field's value, or "".
  # A missing, empty or corrupt pointer file reads as "" (no release).
  local file="$1" field="${2:-current}"
  [ -s "$file" ] || return 0
  PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
    "$NET_CONFIG_PY" -c '
import json
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        data = json.load(handle)
    value = data.get(sys.argv[2]) if isinstance(data, dict) else None
    print(value if isinstance(value, str) else "")
except (OSError, ValueError):
    print("")
' "$file" "$field"
}

manifest_field() {
  # manifest_field <manifest.json> <field> : top-level string field
  sed -n "s/.*\"$2\": \"\([^\"]*\)\".*/\1/p" "$1" | head -1
}

compose_with() {
  local env_file="$1"
  shift
  # t064: Caddy's forward_auth proof reaches compose interpolation only
  # through this process environment, read from the secret file at call
  # time; it is never written into the release env file or printed.
  local edge_proof=""
  if [ -n "${SECRETS_DIR:-}" ] && [ -s "$SECRETS_DIR/edge_proof_key" ]; then
    edge_proof="$(cat "$SECRETS_DIR/edge_proof_key")"
  fi
  CBROWSER_EDGE_PROOF_SECRET="$edge_proof" \
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

deploy_up_and_verify() {
  # deploy_up_and_verify <release_id> : up --wait + readiness gate.
  local release_id="$1"
  local env_file="$RELEASES_DIR/$release_id.env"
  if ! compose_with "$env_file" up -d --no-build --wait --wait-timeout "$UP_WAIT_TIMEOUT"; then
    echo "compose up did not reach a healthy state within ${UP_WAIT_TIMEOUT}s (release $release_id)" >&2
    # Read-only per-Profile diagnostics for the failure report (single
    # readiness snapshot, no new reconcile, no polling); the deploy is a
    # failure regardless of what the probe returns here.
    probe_exec "$env_file" report || true
    return 1
  fi
  if ! verify_readiness "$env_file"; then
    echo "readiness verification failed for release $release_id; previous release remains current" >&2
    return 1
  fi
}

activate_release() {
  # activate_release <release_id> : move current/previous pointers after
  # a verified deploy or rollback.  A single JSON pointer file, written
  # once via the fsyncing atomic writer (A43, AC-017): a crash mid-write
  # leaves either the old pointer or the new one, never a torn file and
  # never a current without its previous.  Atomic, and never touches data.
  local release_id="$1"
  PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" \
    "$NET_CONFIG_PY" -c '
import json
import sys
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

path = Path(sys.argv[1])
release_id = sys.argv[2]
current = previous = None
if path.is_file():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            current = data.get("current")
            previous = data.get("previous")
    except (OSError, ValueError):
        pass
if not isinstance(current, str):
    current = None
if not isinstance(previous, str):
    previous = None
if current and current != release_id:
    previous = current
atomic_write_text(
    path,
    json.dumps({"current": release_id, "previous": previous}) + "\n",
)
' "$POINTER_FILE" "$release_id"
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
  [ -f "$ROOT/src/backend/cbrowser/network_config.py" ] || \
    missing+=("network config generator: src/backend/cbrowser/network_config.py")
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
  for name in supervisor_key agent_key gateway_key gateway_api_key edge_proof_key viewer_grant_key; do
    file="$SECRETS_DIR/$name"
    if [ ! -s "$file" ]; then
      ( umask 077; openssl rand -hex 32 > "$file" )
    fi
    chmod 600 "$file"
  done
  chmod 600 "$SECRETS_DIR/admin_password"
}

check_prefix_conflict() {
  # Refuse when another deployment already owns our resource prefix: its
  # Supervisor would treat this instance's Profiles as orphans (and vice
  # versa).  Scan ALL containers (running or stopped) and attribute by
  # container name and prefix label, not just by the one labelled fixed
  # service: an instance whose Gateway has exited still owns its prefix
  # through its Supervisor and Profile containers.
  #
  # Ownership is decided ONLY by the com.cbrowser.instance-id label
  # (A59/AC-021, strict t069): a prefix-matching container is ours
  # when — and only when — its instance-id equals this instance's
  # CBROWSER_INSTANCE_ID. A missing or mismatched instance-id is
  # foreign in every case, including the same compose project: the
  # project name alone never proves ownership.
  #
  # Media subnet pools (A3) are checked on the same scan, independent of
  # prefix: any other deployment whose pool overlaps ours refuses the
  # deploy, even when its prefix differs.
  local rows name project row_prefix role deployment_id pool
  rows="$(docker ps -a --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.cbrowser.prefix"}}\t{{.Label "com.cbrowser.role"}}\t{{.Label "com.cbrowser.instance-id"}}\t{{.Label "com.cbrowser.media-subnet-pool"}}')"
  while IFS=$'\t' read -r name project row_prefix role deployment_id pool; do
    [ -n "$name" ] || continue
    if [ -n "$pool" ] && [ -n "$CBROWSER_MEDIA_SUBNET_POOL" ]; then
      case "$deployment_id" in
        "$CBROWSER_INSTANCE_ID") ;;
        *)
          if pools_overlap "$CBROWSER_MEDIA_SUBNET_POOL" "$pool"; then
            echo "Refusing to start: media subnet pool '$CBROWSER_MEDIA_SUBNET_POOL' overlaps pool '$pool' used by container '$name' (another deployment)." >&2
            echo "Choose a different CBROWSER_PREFIX/CBROWSER_DATA_ROOT for this instance (the pool derives from the instance identity)." >&2
            exit 1
          fi
          ;;
      esac
    fi
    case "$name" in
      "$PREFIX"-*) ;;
      *) [ "$row_prefix" = "$PREFIX" ] || continue ;;
    esac
    if [ -n "$CBROWSER_INSTANCE_ID" ] && [ "$deployment_id" = "$CBROWSER_INSTANCE_ID" ]; then
      continue
    fi
    echo "Refusing to start: resource prefix '$PREFIX' is already used by instance (compose project '$project', container '$name')." >&2
    echo "Choose a different CBROWSER_PREFIX/CBROWSER_COMPOSE_PROJECT for this instance." >&2
    exit 1
  done <<< "$rows"
}

load_release_identity() {
  # load_release_identity <env_file> : adopt the instance identity
  # recorded in a release env (project, prefix, port, edge subnet,
  # trusted proxy CIDRs, data root, secrets dir).  Compose interpolation
  # prefers the shell environment over --env-file values, so a rollback
  # must run with the TARGET release's identity, never with whatever the
  # caller's shell exports.  Origin is NOT part of the identity: the
  # Origin whitelist is derived from the deployment port (t054), never
  # from CBROWSER_PUBLIC_ORIGIN / CBROWSER_ALLOWED_ORIGINS (t042: both
  # retired, no compat — old releases needing them are refused by the
  # stamp check below, not adapted).  There is no bind host anymore:
  # Caddy and the Stream UDP mux always bind loopback.
  local env_file="$1" line key value
  while IFS= read -r line; do
    case "$line" in
      CBROWSER_COMPOSE_PROJECT=*|CBROWSER_PREFIX=*|CBROWSER_HTTPS_PORT=*|\
      CBROWSER_EDGE_SUBNET=*|CBROWSER_TRUSTED_PROXY_CIDRS=*|\
      CBROWSER_DATA_ROOT=*|CBROWSER_SECRETS_DIR=*|\
      CBROWSER_INSTANCE_ID=*|CBROWSER_MEDIA_SUBNET_POOL=*|CBROWSER_FONTS_DIR=*|\
      CBROWSER_ENGINE_BUILD=*|CBROWSER_ENGINE_VERSION=*|\
      CBROWSER_ENGINE_BINARY_SHA256=*|CLOAKBROWSER_AUTO_UPDATE=*)
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
        ;;
    esac
  done < "$env_file"
  PROJECT="$CBROWSER_COMPOSE_PROJECT"
  PREFIX="$CBROWSER_PREFIX"
  HTTPS_PORT="$CBROWSER_HTTPS_PORT"
  DATA_ROOT="$CBROWSER_DATA_ROOT"
  SECRETS_DIR="$CBROWSER_SECRETS_DIR"
  FONTS_DIR="${CBROWSER_FONTS_DIR:-$ROOT/data/fonts}"
}

build_api_image() {
  # Build the API image first: the schema-generation check and the
  # database backup run inside it, before any container is started.
  # Building an image changes no data.  Sets API_IMAGE_ID.
  local release_id="$1"
  local tag_api="cbrowser-api:$release_id"
  # Attestation manifests embed per-invocation build metadata, so an
  # otherwise identical rebuild would get a different image ID and force
  # compose to recreate healthy services. Disable them: the release
  # manifest pins the rootfs/config digest, which is what reproducibility
  # and rollback identity depend on (t032 AC-001/AC-010).  Same flags in
  # build_and_record_release below.
  docker build --provenance=false --sbom=false -t "$tag_api" -f config/docker/api_runtime/Dockerfile .
  API_IMAGE_ID="$(docker image inspect --format '{{.Id}}' "$tag_api")"
}

build_and_record_release() {
  # Builds each remaining image once, writes <id>.env + <id>.json under releases/.
  local release_id="$1"
  local tag_gateway="cbrowser-gateway:$release_id"
  local tag_supervisor="cbrowser-supervisor:$release_id" tag_browser="cbrowser-browser:$release_id"
  local tag_stream="cbrowser-stream:$release_id"

  docker build --provenance=false --sbom=false -t "$tag_browser" -f config/docker/browser_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_stream" -f config/docker/stream_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_supervisor" -f config/docker/supervisor_runtime/Dockerfile .
  docker build --provenance=false --sbom=false -t "$tag_gateway" -f config/docker/gateway_runtime/Dockerfile .
  if ! docker image inspect "$CADDY_REF" >/dev/null 2>&1; then
    docker pull "$CADDY_REF"
  fi

  local api_id gateway_id supervisor_id browser_id stream_id caddy_id
  api_id="$API_IMAGE_ID"
  gateway_id="$(docker image inspect --format '{{.Id}}' "$tag_gateway")"
  supervisor_id="$(docker image inspect --format '{{.Id}}' "$tag_supervisor")"
  browser_id="$(docker image inspect --format '{{.Id}}' "$tag_browser")"
  stream_id="$(docker image inspect --format '{{.Id}}' "$tag_stream")"
  caddy_id="$(docker image inspect --format '{{.Id}}' "$CADDY_REF")"

  local compose_sha caddyfile_sha frontend_sha migration
  compose_sha="$(sha256_of_file "$ROOT/compose.yaml")"
  # t054: the fingerprint hashes the FINAL Caddyfile product rendered for
  # this deploy (data root), never the generator source: a generator
  # change that renders the same file leaves the fingerprint unchanged,
  # while a port change re-renders and changes it.
  caddyfile_sha="$(sha256_of_file "$DATA_ROOT/network/Caddyfile")"
  frontend_sha="$(frontend_fingerprint)"
  migration="$(migration_head)"

  mkdir -p "$RELEASES_DIR"
  cat <<ENV | atomic_write "$RELEASES_DIR/$release_id.env"
CBROWSER_COMPOSE_PROJECT=$PROJECT
CBROWSER_PREFIX=$PREFIX
CBROWSER_HTTPS_PORT=$HTTPS_PORT
CBROWSER_EDGE_SUBNET=$CBROWSER_EDGE_SUBNET
CBROWSER_TRUSTED_PROXY_CIDRS=$CBROWSER_EDGE_SUBNET
CBROWSER_DATA_ROOT=$DATA_ROOT
CBROWSER_SECRETS_DIR=$SECRETS_DIR
CBROWSER_FONTS_DIR=$FONTS_DIR
CBROWSER_INSTANCE_ID=$CBROWSER_INSTANCE_ID
CBROWSER_MEDIA_SUBNET_POOL=$CBROWSER_MEDIA_SUBNET_POOL
CBROWSER_API_IMAGE=$api_id
CBROWSER_GATEWAY_IMAGE=$gateway_id
CBROWSER_SUPERVISOR_IMAGE=$supervisor_id
CBROWSER_BROWSER_IMAGE=$browser_id
CBROWSER_STREAM_IMAGE=$stream_id
CBROWSER_CADDY_IMAGE=$caddy_id
CBROWSER_CADDYFILE_SHA256=$caddyfile_sha
CBROWSER_FRONTEND_SHA256=$frontend_sha
CLOAKBROWSER_AUTO_UPDATE=$CLOAKBROWSER_AUTO_UPDATE
CBROWSER_ENGINE_BUILD=$CBROWSER_ENGINE_BUILD
CBROWSER_ENGINE_VERSION=$CBROWSER_ENGINE_VERSION
CBROWSER_ENGINE_BINARY_SHA256=$CBROWSER_ENGINE_BINARY_SHA256
ENV

  local created_at database_backup_json engine_json
  created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  if [ -n "$DATABASE_BACKUP_PATH" ]; then
    database_backup_json="\"$DATABASE_BACKUP_PATH\""
  else
    database_backup_json=null
  fi
  engine_json="$(PYTHONPATH="$ROOT/src/backend${PYTHONPATH:+:$PYTHONPATH}" "$NET_CONFIG_PY" -c '
import json, os
print(json.dumps({
    "cloakbrowser_package": os.environ.get("CBROWSER_CLOAKBROWSER_PACKAGE", ""),
    "platform_tag": os.environ.get("CBROWSER_ENGINE_PLATFORM", ""),
    "engine_build": os.environ.get("CBROWSER_ENGINE_BUILD", ""),
    "archive_sha256": os.environ.get("CBROWSER_ENGINE_ARCHIVE_SHA256", ""),
    "binary_sha256": os.environ.get("CBROWSER_ENGINE_BINARY_SHA256", "") or None,
    "integrity_mechanism": os.environ.get("CBROWSER_ENGINE_INTEGRITY_MECHANISM", ""),
    "trust_source": os.environ.get("CBROWSER_ENGINE_TRUST_SOURCE", ""),
    "auto_update_disabled": True,
}))
')"
  engine_json="${engine_json:-null}"
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
  "engine": $engine_json,
  "compose_sha256": "$compose_sha",
  "caddyfile_sha256": "$caddyfile_sha",
  "frontend_sha256": "$frontend_sha",
  "migration_version": "$migration",
  "database_backup": $database_backup_json,
  "capabilities": {"readiness": true, "reconcile_all": true},
  "instance": {"project": "$PROJECT", "prefix": "$PREFIX", "https_port": $HTTPS_PORT, "instance_id": "$CBROWSER_INSTANCE_ID", "media_subnet_pool": "$CBROWSER_MEDIA_SUBNET_POOL", "edge_subnet": "$CBROWSER_EDGE_SUBNET"}
}
JSON
}

cmd_deploy() {
  check_prerequisites
  check_engine_artifact_preflight
  derive_instance_identity
  check_prefix_conflict
  check_edge_subnet_conflict

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

  # The API image is built first so the schema check and the backup can
  # run inside it; building an image changes no data, and no container
  # is started and no pointer moves before the checks below pass.
  build_api_image "$release_id"
  check_database_schema_generation "$API_IMAGE_ID"
  check_legacy_host_database
  check_font_sets_preflight
  backup_database "$API_IMAGE_ID"

  ensure_internal_secrets
  mkdir -p "$DATA_ROOT"/{profiles,runtime,runtime-events,artifacts,spool,control,engine-cache/geoip}

  # t054: render the Caddyfile for the deploy port (the only network
  # configuration step) and export the derived trusted proxy CIDRs
  # (the edge subnet) for API + Gateway. No bind host: loopback only.
  eval "$(network_config render --network-dir "$DATA_ROOT/network" --https-port "$HTTPS_PORT")"
  export CBROWSER_HTTPS_PORT="$HTTPS_PORT"
  export CBROWSER_TRUSTED_PROXY_CIDRS="$CBROWSER_EDGE_SUBNET"

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
    target="$(read_pointer "$POINTER_FILE" previous)"
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
  check_engine_artifact_preflight
  # AC-002 (t035): fail closed before anything changes when the live
  # database belongs to the retired schema generation.  The stamp is read
  # inside the target release's API image.
  local target_api
  target_api="$(sed -n 's/^CBROWSER_API_IMAGE=//p' "$target_env")"
  if [ -z "$target_api" ]; then
    echo "Refusing rollback: CBROWSER_API_IMAGE missing from target release env." >&2
    exit 1
  fi
  check_database_schema_generation "$target_api"
  local current
  current="$(read_pointer "$POINTER_FILE")"
  if [ -z "$current" ] || [ ! -f "$RELEASES_DIR/$current.json" ]; then
    echo "No current release recorded; nothing to roll back from." >&2
    exit 1
  fi
  if [ "$target" = "$current" ]; then
    echo "Rollback target '$target' is already the current release." >&2
    exit 1
  fi
  # Refuse BEFORE changing anything when the target cannot be verified
  # by the current acceptance contract, or belongs to a different
  # (retired) schema generation (t035 AC-002).
  if ! grep -q '"readiness": true' "$target_manifest"; then
    echo "Refusing rollback to '$target': release does not offer the readiness capability required for acceptance." >&2
    exit 1
  fi
  local target_migration chain
  target_migration="$(manifest_field "$target_manifest" migration_version)"
  if [ -z "$target_migration" ]; then
    echo "Refusing rollback: migration version missing from target release manifest." >&2
    exit 1
  fi
  # The rollback floor is decided by the Alembic revision chain, not by
  # lexical string comparison.  Only a release whose migration head is a
  # member of the shipped chain (the current schema generation, rooted at
  # the t035 baseline) may be a rollback target.  A release built from the
  # retired 0001-0009 chain is refused here, before any container is
  # started or pointer moved; cross-generation rollback has no
  # ALLOWED_ORIGINS compat and must rebuild the data directory instead.
  chain="$(current_revision_chain)"
  if ! grep -qxF "$target_migration" <<< "$chain"; then
    echo "Refusing rollback to '$target': its migration head '$target_migration' is not in the current Alembic revision chain (baseline $BASELINE_REVISION)." >&2
    echo "Releases from the retired 0001-0009 schema generation cannot be rollback targets; rebuild the data directory from scratch instead." >&2
    exit 1
  fi
  # P1-C: no downgrade — the target head must equal the live database
  # stamp read right now (read-only, before any change).  A stale
  # same-generation head (target in chain but older than the stamped head)
  # and a retired-generation release are both refused here.  An old t042
  # release that would need the deleted ALLOWED_ORIGINS is refused by this
  # equality (its head cannot equal a current-generation stamp); no compat
  # is provided — rebuild the data directory instead.  An absent/unstamped
  # database is left to API startup (fresh install path).
  local live_stamp
  if ! live_stamp="$(current_db_stamp "$target_api")"; then
    exit 1
  fi
  if [ -n "$live_stamp" ] && [ "$target_migration" != "$live_stamp" ]; then
    echo "Refusing rollback to '$target': target migration head '$target_migration' != live database stamp '$live_stamp'; no downgrade migration exists." >&2
    echo "Rebuild the data directory from scratch instead; no ALLOWED_ORIGINS compat is provided." >&2
    exit 1
  fi
  # Rollback consumes compose_sha256: the working-tree compose.yaml must
  # still match the target release's fingerprint.  Deploying old images
  # with a new compose file would be a mixed, unaccepted configuration, so
  # refuse before anything changes instead of silently mixing generations.
  local target_compose current_compose
  target_compose="$(manifest_field "$target_manifest" compose_sha256)"
  if [ -z "$target_compose" ]; then
    echo "Refusing rollback: compose_sha256 missing from target release manifest." >&2
    exit 1
  fi
  current_compose="$(sha256_of_file "$ROOT/compose.yaml")"
  if [ "$target_compose" != "$current_compose" ]; then
    echo "Refusing rollback to '$target': working-tree compose.yaml (sha256 $current_compose) != target compose_sha256 ($target_compose); old images with a new compose file would be mixed." >&2
    exit 1
  fi

  check_prefix_conflict
  check_edge_subnet_conflict
  # t054: rollback re-renders the Caddyfile from the TARGET release's
  # recorded port and verifies it against the target manifest's
  # caddyfile_sha256 before anything starts: a rollback must serve the
  # target's edge, not the current release's. This runs after the
  # conflict checks so a refused rollback leaves the disk untouched.
  # t054 R1 f002: render into a scratch directory first and only move
  # the file into $DATA_ROOT/network after the sha matches — rendering
  # straight into the live directory rewrote the Caddyfile even when
  # the sha check then refused the rollback.
  local target_caddy_sha rendered_caddy_sha tmp_network_dir
  target_caddy_sha="$(manifest_field "$target_manifest" caddyfile_sha256)"
  if [ -z "$target_caddy_sha" ]; then
    echo "Refusing rollback: caddyfile_sha256 missing from target release manifest." >&2
    exit 1
  fi
  tmp_network_dir="$(mktemp -d)"
  eval "$(network_config render --network-dir "$tmp_network_dir" --https-port "$HTTPS_PORT")"
  rendered_caddy_sha="$CADDYFILE_SHA256"
  if [ "$rendered_caddy_sha" != "$target_caddy_sha" ]; then
    rm -rf "$tmp_network_dir"
    echo "Refusing rollback: re-rendered Caddyfile sha256 $rendered_caddy_sha != target manifest caddyfile_sha256 $target_caddy_sha." >&2
    exit 1
  fi
  mkdir -p "$DATA_ROOT/network"
  cp "$tmp_network_dir/Caddyfile" "$DATA_ROOT/network/Caddyfile"
  rm -rf "$tmp_network_dir"

  deploy_up_and_verify "$target"
  activate_release "$target"
  echo "Rolled back to release $target and readiness-verified."
  echo "  Manifest: $target_manifest"
}

cmd_restore() {
  # restore <backup-file> : stop the stack and copy a backup back into the
  # database volume (stale -wal/-shm removed first by db_restore.py).
  # The backup file itself is never deleted.  The user re-deploys
  # afterwards to start the stack against the restored database.
  local backup_file="${1:-}"
  if [ -z "$backup_file" ]; then
    echo "usage: $0 restore <backup-file>" >&2
    exit 2
  fi
  if [ ! -f "$backup_file" ]; then
    echo "Restore backup '$backup_file' does not exist." >&2
    exit 1
  fi
  local current
  current="$(read_pointer "$POINTER_FILE")"
  if [ -z "$current" ] || [ ! -f "$RELEASES_DIR/$current.env" ]; then
    echo "No current release recorded; deploy once first so an API image exists to run the restore." >&2
    exit 1
  fi
  # The restore runs against the current release's identity (its prefix
  # names the database volume, its API image runs the restore container).
  load_release_identity "$RELEASES_DIR/$current.env"
  local api_image
  api_image="$(sed -n 's/^CBROWSER_API_IMAGE=//p' "$RELEASES_DIR/$current.env")"
  if [ -z "$api_image" ]; then
    echo "Refusing restore: CBROWSER_API_IMAGE missing from current release env." >&2
    exit 1
  fi
  compose_with "$RELEASES_DIR/$current.env" down
  local backup_abs backup_name
  backup_abs="$(cd "$(dirname "$backup_file")" && pwd)/$(basename "$backup_file")"
  backup_name="$(basename "$backup_file")"
  docker run --rm \
    -v "$(db_volume_name):/db" \
    -v "$(dirname "$backup_abs"):/backup:ro" \
    -v "$ROOT/scripts:/scripts:ro" \
    "$api_image" python3 /scripts/db_restore.py \
    --backup "/backup/$backup_name" --db /db/cbrowser.db
  echo "Database restored from $backup_file into volume $(db_volume_name)."
  echo "Re-deploy to start the stack against the restored database."
}

cmd_env_backup() {
  # env-backup [point-dir] : see the header.  Runs restore_point.py in a
  # throwaway API container with the database volume, the data root
  # (mounted at /data, the API container's own view, so recorded
  # user_data_dir values resolve) and the scripts directory mounted.
  local current api_image point_dir point_name
  current="$(read_pointer "$POINTER_FILE")"
  if [ -z "$current" ] || [ ! -f "$RELEASES_DIR/$current.env" ]; then
    echo "No current release recorded; deploy once first so an API image exists to run the backup." >&2
    exit 1
  fi
  load_release_identity "$RELEASES_DIR/$current.env"
  api_image="$(sed -n 's/^CBROWSER_API_IMAGE=//p' "$RELEASES_DIR/$current.env")"
  if [ -z "$api_image" ]; then
    echo "Refusing env-backup: CBROWSER_API_IMAGE missing from current release env." >&2
    exit 1
  fi
  point_dir="${1:-$ROOT/data/backups/restore-points/point-$(date +%Y%m%dT%H%M%S)}"
  mkdir -p "$(dirname "$point_dir")"
  point_name="$(basename "$point_dir")"
  docker run --rm \
    -v "$(db_volume_name):/db" \
    -v "$DATA_ROOT:/data" \
    -v "$SECRETS_DIR:/secrets:ro" \
    -v "$(dirname "$point_dir"):/points" \
    -v "$ROOT/scripts:/scripts:ro" \
    "$api_image" python3 /scripts/restore_point.py create \
      --db /db/cbrowser.db --data-root /data \
      --out "/points/$point_name" --secrets-dir /secrets --label deploy.sh
  echo "Restore point written to $point_dir."
}

cmd_env_restore() {
  # env-restore <point-dir> : see the header.  The stack is stopped
  # first (the restore tool's precondition, same as cmd_restore); the
  # switch journal lives in the data root so an interrupted switch is
  # rolled back by the next invocation before anything else happens.
  local point_dir="${1:-}"
  if [ -z "$point_dir" ]; then
    echo "usage: $0 env-restore <point-dir>" >&2
    exit 2
  fi
  if [ ! -f "$point_dir/manifest.json" ]; then
    echo "Restore point '$point_dir' does not exist or has no manifest.json." >&2
    exit 1
  fi
  local current api_image point_abs point_name
  current="$(read_pointer "$POINTER_FILE")"
  if [ -z "$current" ] || [ ! -f "$RELEASES_DIR/$current.env" ]; then
    echo "No current release recorded; deploy once first so an API image exists to run the restore." >&2
    exit 1
  fi
  load_release_identity "$RELEASES_DIR/$current.env"
  api_image="$(sed -n 's/^CBROWSER_API_IMAGE=//p' "$RELEASES_DIR/$current.env")"
  if [ -z "$api_image" ]; then
    echo "Refusing env-restore: CBROWSER_API_IMAGE missing from current release env." >&2
    exit 1
  fi
  compose_with "$RELEASES_DIR/$current.env" down
  point_abs="$(cd "$point_dir" && pwd)"
  point_name="$(basename "$point_abs")"
  docker run --rm \
    -v "$(db_volume_name):/db" \
    -v "$DATA_ROOT:/data" \
    -v "$(dirname "$point_abs"):/points:ro" \
    -v "$ROOT/scripts:/scripts:ro" \
    "$api_image" python3 /scripts/restore_point.py restore \
      --point "/points/$point_name" --db /db/cbrowser.db \
      --data-root /data --journal /data/restore-journal.json
  echo "Environment restored from $point_dir into volume $(db_volume_name) and $DATA_ROOT."
  echo "Re-deploy to start the stack against the restored environment."
}

cmd_status() {
  local current previous
  current="$(read_pointer "$POINTER_FILE")"
  previous="$(read_pointer "$POINTER_FILE" previous)"
  echo "current: ${current:-<none>}"
  echo "previous: ${previous:-<none>}"
  if [ -n "$current" ] && [ -f "$RELEASES_DIR/$current.json" ]; then
    echo "manifest: $RELEASES_DIR/$current.json"
  fi
}

case "$COMMAND" in
  deploy) cmd_deploy ;;
  rollback) cmd_rollback "$@" ;;
  restore) cmd_restore "$@" ;;
  env-backup) cmd_env_backup "$@" ;;
  env-restore) cmd_env_restore "$@" ;;
  status) cmd_status ;;
  *) echo "usage: $0 [deploy|rollback [release_id]|restore <backup-file>|env-backup [point-dir]|env-restore <point-dir>|status]" >&2; exit 2 ;;
esac
