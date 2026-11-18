"""Host-directory to named-volume storage migration (t080 / ADR 029).

Pure-logic core: the operator runs the CLI (scripts/storage_migration.py)
inside a one-shot container with the legacy host directories mounted
read-only and the target volumes mounted at explicit paths.  Nothing in
here talks to Docker.

Safety contract (task t080):

* inventory/dry-run changes nothing and reports per-file SHA-256 digests;
* a run refuses while any actual writer holds a source file open
  (lsof-based detection; when detection is unavailable the operator must
  explicitly confirm the stack is stopped);
* capacity and readability/ownership are validated before any copy;
* an environment restore point must verify (every recorded digest) before
  the switch phase may move a single byte — prove the backup is
  restorable first, then rewrite pointers/data;
* the copy goes to a staging tree inside each target volume, is fully
  digest-verified there, and only then renamed into place; every phase
  transition is journaled so an interrupted run resumes or rolls back
  idempotently, and the source tree is never modified or deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from cbrowser.shared.atomic_write import atomic_write_text

SKIP_NAMES = frozenset({"SingletonLock", "SingletonCookie", "SingletonSocket"})
STAGING_PREFIX = ".migration-staging-"
PHASES = (
    "planned",
    "inventoried",
    "backup_verified",
    "staged",
    "verified",
    "switched",
    "done",
)


class MigrationError(RuntimeError):
    """A migration precondition failed; nothing was switched."""


class WriterActiveError(MigrationError):
    """A source file is held open by a live process."""


@dataclass(frozen=True)
class FileRecord:
    source_root: str  # "data" | "fonts" (which legacy root)
    source_rel: str  # POSIX path relative to that root
    target_kind: str  # "data" | "fonts" | "runtime"
    target_rel: str  # POSIX path relative to the target volume root
    size: int
    sha256: str


@dataclass(frozen=True)
class DirRecord:
    source_root: str  # "data" | "fonts"
    source_rel: str  # POSIX path relative to that root (never "" itself)
    target_kind: str  # "data" | "fonts" | "runtime"
    target_rel: str  # POSIX path relative to the target volume root
    mode: int


@dataclass
class MigrationPlan:
    records: list[FileRecord]
    source_data_root: str
    source_fonts_dir: str
    dirs: list[DirRecord] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "MigrationPlan":
        """An explicit no-content plan (rollback journal adoption only)."""
        return cls(records=[], source_data_root="", source_fonts_dir="")

    @property
    def total_bytes(self) -> int:
        return sum(record.size for record in self.records)

    def digest(self) -> str:
        canonical = json.dumps(
            {
                "files": [
                    {
                        "source_root": r.source_root,
                        "source_rel": r.source_rel,
                        "target_kind": r.target_kind,
                        "target_rel": r.target_rel,
                        "size": r.size,
                        "sha256": r.sha256,
                    }
                    for r in self.records
                ],
                "dirs": [
                    {
                        "source_root": d.source_root,
                        "source_rel": d.source_rel,
                        "target_kind": d.target_kind,
                        "target_rel": d.target_rel,
                        "mode": d.mode,
                    }
                    for d in self.dirs
                ],
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _classify_data_rel(rel: str) -> tuple[str, str]:
    """Map a legacy data-root-relative path to (target kind, target rel)."""
    if rel == "runtime" or rel.startswith("runtime/"):
        return "runtime", rel[len("runtime/"):] if rel != "runtime" else ""
    if rel == "control/gates" or rel.startswith("control/gates/"):
        rest = rel[len("control/gates/"):] if rel != "control/gates" else ""
        return "runtime", f"gates/{rest}" if rest else "gates"
    return "data", rel


def _walk(
    root: Path, source_root: str
) -> tuple[list[FileRecord], list[DirRecord]]:
    """Inventory one legacy root; fail closed on any gap (t080 f002/f006).

    A missing or non-directory source root is an operator error, never an
    empty inventory: silently planning zero files would let a mistyped
    path "migrate" nothing and report success.
    """
    records: list[FileRecord] = []
    dirs: list[DirRecord] = []
    problems: list[str] = []
    if not root.is_dir():
        raise MigrationError(
            f"source root {root} is missing or not a directory; "
            "refusing to inventory a nonexistent source"
        )

    def _onerror(exc: OSError) -> None:
        problems.append(f"directory enumeration failed: {exc}")

    for directory, dirnames, filenames in os.walk(
        root, followlinks=False, onerror=_onerror
    ):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_NAMES)
        base = Path(directory)
        for name in dirnames:
            child = base / name
            if child.is_symlink():
                problems.append(f"symlink directory: {child}")
                continue
            rel = child.relative_to(root).as_posix()
            if source_root == "data":
                target_kind, target_rel = _classify_data_rel(rel)
                if not target_rel:
                    continue
            else:
                target_kind, target_rel = "fonts", rel
            try:
                mode = child.stat().st_mode & 0o7777
            except OSError as exc:
                problems.append(f"unreadable directory: {rel} ({exc.strerror})")
                continue
            dirs.append(
                DirRecord(
                    source_root=source_root,
                    source_rel=rel,
                    target_kind=target_kind,
                    target_rel=target_rel,
                    mode=mode,
                )
            )
        for name in sorted(filenames):
            if name in SKIP_NAMES:
                continue
            child = base / name
            rel = child.relative_to(root).as_posix()
            if child.is_symlink():
                problems.append(f"symlink file: {rel}")
                continue
            try:
                size = child.stat().st_size
                digest = _sha256_file(child)
            except OSError as exc:
                problems.append(f"unreadable file: {rel} ({exc.strerror})")
                continue
            if source_root == "data":
                target_kind, target_rel = _classify_data_rel(rel)
                if not target_rel:
                    continue
            else:
                target_kind, target_rel = "fonts", rel
            records.append(
                FileRecord(
                    source_root=source_root,
                    source_rel=rel,
                    target_kind=target_kind,
                    target_rel=target_rel,
                    size=size,
                    sha256=digest,
                )
            )
    if problems:
        raise MigrationError(
            "source inventory failed closed: " + "; ".join(problems[:20])
        )
    return records, dirs


def build_plan(source_data_root: Path, source_fonts_dir: Path) -> MigrationPlan:
    records, data_dirs = _walk(source_data_root, "data")
    font_records, font_dirs = _walk(source_fonts_dir, "fonts")
    records = records + font_records
    records.sort(key=lambda r: (r.target_kind, r.target_rel))
    dirs = data_dirs + font_dirs
    dirs.sort(key=lambda d: (d.target_kind, d.target_rel))
    return MigrationPlan(
        records=records,
        source_data_root=str(source_data_root),
        source_fonts_dir=str(source_fonts_dir),
        dirs=dirs,
    )


def detect_writers(roots: list[Path]) -> list[str] | None:
    """Return processes holding source files open, or None if detection
    is unavailable *or failed* (t080 f005: an lsof error must not be
    read as "no writers" — that is the fail-open mirror of the missing-
    lsof case and takes the same explicit-confirmation path)."""
    if shutil.which("lsof") is None:
        return None
    offenders: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        try:
            result = subprocess.run(
                ["lsof", "-Fpc", "+D", str(root)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        # lsof: 0 = matches found, 1 = no matches (with clean stderr).
        # Anything else, or diagnostics on stderr, means the enumeration
        # itself failed and its empty stdout proves nothing.
        if result.returncode not in (0, 1) or (
            result.returncode == 1 and result.stderr.strip()
        ):
            return None
        if result.returncode == 1:
            continue
        current: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if line.startswith("p"):
                current = {"pid": line[1:]}
            elif line.startswith("c"):
                offenders.append(f"pid {current.get('pid', '?')} ({line[1:]})")
    return offenders


def verify_restore_point(point_dir: Path) -> dict:
    """Prove an environment restore point's recorded bytes are intact.

    Re-checks the database digest and every per-Profile file digest in
    the point manifest (the same evidence restore_point.py restore would
    rely on).  Raises MigrationError listing the first problems found.
    Returns the manifest so callers can verify source ownership (the
    manifest records the data root the point was taken from).
    """
    manifest_path = point_dir / "manifest.json"
    if not manifest_path.is_file():
        raise MigrationError(f"restore point {point_dir} has no manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MigrationError(f"restore point manifest unreadable: {exc}") from None
    if manifest.get("kind") != "cbrowser-restore-point":
        raise MigrationError("restore point manifest kind is not cbrowser-restore-point")
    problems: list[str] = []
    db = manifest.get("db") or {}
    db_file = point_dir / str(db.get("file", ""))
    if not db_file.is_file():
        problems.append("database file missing from restore point")
    elif db_file.stat().st_size != db.get("size") or _sha256_file(db_file) != db.get(
        "sha256"
    ):
        problems.append("database digest mismatch in restore point")
    for profile in manifest.get("profiles") or []:
        rel_dir = profile.get("dir")
        if not rel_dir:
            continue
        base = point_dir / rel_dir
        for rel, meta in (profile.get("files") or {}).items():
            path = base / rel
            if "link" in meta:
                if not path.is_symlink():
                    problems.append(f"{rel_dir}/{rel}: symlink missing")
                continue
            if not path.is_file():
                problems.append(f"{rel_dir}/{rel}: missing")
            elif path.stat().st_size != meta.get("size") or _sha256_file(
                path
            ) != meta.get("sha256"):
                problems.append(f"{rel_dir}/{rel}: digest mismatch")
            if len(problems) >= 20:
                break
    if problems:
        raise MigrationError(
            "restore point verification failed: " + "; ".join(problems[:20])
        )
    return manifest


VOLUME_MARKER = ".cbrowser-volume.json"


def read_volume_identity(root: Path) -> str | None:
    """Return the volume name stamped at a volume root, or None."""
    try:
        data = json.loads((root / VOLUME_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and isinstance(data.get("volume"), str):
        return data["volume"]
    return None


@dataclass
class MigrationRunner:
    plan: MigrationPlan
    targets: dict[str, Path]  # kind -> volume root
    journal_path: Path
    restore_point: Path | None = None
    writer_detector: object = None  # callable(roots) -> list[str] | None
    confirm_stack_stopped: bool = False
    expected_prefix: str | None = None  # deployment resource prefix (f003)
    run_id: str = field(default="")

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = hashlib.sha256(
                (self.plan.digest() + str(self.journal_path)).encode()
            ).hexdigest()[:12]
        self._journal: dict = {}

    # -- journal ------------------------------------------------------
    def _save_journal(self, phase: str) -> None:
        # Identity fields are write-once per journal (t080 f004): a
        # rollback runner built from an empty plan must never overwrite
        # the original run's run_id/plan_digest/total_bytes.
        self._journal.setdefault("run_id", self.run_id)
        self._journal.setdefault("plan_digest", self.plan.digest())
        self._journal.setdefault("total_bytes", self.plan.total_bytes)
        self._journal["phase"] = phase
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            self.journal_path,
            json.dumps(self._journal, indent=2, sort_keys=True) + "\n",
        )

    def _load_journal(self) -> None:
        if self.journal_path.is_file():
            try:
                data = json.loads(self.journal_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
            if isinstance(data, dict):
                self._journal = data

    @property
    def phase(self) -> str:
        return str(self._journal.get("phase", ""))

    def _staging_dir(self, kind: str) -> Path:
        return self.targets[kind] / f"{STAGING_PREFIX}{self.run_id}"

    # -- phases ---------------------------------------------------------
    def run(self) -> str:
        """Execute (or resume) the migration; returns the final phase."""
        self._load_journal()
        # Plan identity is checked before ANY terminal-state shortcut
        # (t080 f010): a different plan reusing a completed or rolled-
        # back journal must fail loudly, never inherit its phase.
        if self._journal and self._journal.get("plan_digest") != self.plan.digest():
            raise MigrationError(
                "journal belongs to a different plan; refusing to resume"
            )
        if self.phase == "done":
            return "done"
        if self.phase == "rolled_back":
            # Rollback removed everything the run placed, so a fresh run
            # with the same plan starts over from an empty journal
            # (t080 f007: previously this fell through every phase
            # branch and silently returned "rolled_back" having copied
            # nothing).
            self._journal = {}
        if self.phase in ("", "planned"):
            self._check_ownership()
            self._check_writers()
            self._check_capacity()
            self._save_journal("planned")
        if self.phase == "planned":
            fresh = build_plan(
                Path(self.plan.source_data_root), Path(self.plan.source_fonts_dir)
            )
            if fresh.digest() != self.plan.digest():
                raise MigrationError(
                    "source tree changed after planning; re-run inventory"
                )
            self._save_journal("inventoried")
        if self.phase == "inventoried":
            if self.restore_point is None:
                raise MigrationError(
                    "a verified environment restore point is required before "
                    "the switch; create one with deploy.sh env-backup first"
                )
            manifest = verify_restore_point(self.restore_point)
            self._check_source_ownership(manifest)
            self._save_journal("backup_verified")
        if self.phase == "backup_verified":
            self._stage()
            self._save_journal("staged")
        if self.phase == "staged":
            self._verify_staging()
            self._save_journal("verified")
        if self.phase == "verified":
            self._switch()
            self._save_journal("switched")
        if self.phase == "switched":
            for kind in self.targets:
                shutil.rmtree(self._staging_dir(kind), ignore_errors=True)
            self._save_journal("done")
        return self.phase

    def _check_ownership(self) -> None:
        """AC-004 ownership: every target volume must provably belong to
        the expected deployment (t080 f003).  Volumes are stamped with
        `.cbrowser-volume.json` at layout initialization; a missing or
        mismatched stamp means the operator pointed the migration at
        another deployment's volume — fail before any copy."""
        if not self.expected_prefix:
            return
        from cbrowser.supervisor.storage_layout import volume_name

        for kind, target in self.targets.items():
            expected = volume_name(self.expected_prefix, kind)
            actual = read_volume_identity(target)
            if actual != expected:
                raise MigrationError(
                    f"target {kind} ownership mismatch: expected volume "
                    f"{expected}, found {actual or 'no identity marker'}"
                )

    def _check_source_ownership(self, manifest: dict) -> None:
        """The restore point must have been taken from the very source
        tree being migrated (t080 f003/f009).  The check is anchored in
        content, not paths: the manifest's per-Profile file digests were
        recorded from the source data root, so every recorded file must
        be present in this source tree with the same digest.  (Path
        comparison cannot work — the point is produced in the API
        container, where the data root is /data, while the migration
        mounts the same tree at an arbitrary path.)  A point from
        another deployment fails here even though it verifies on its
        own.  Coverage is bidirectional: the Profile set recorded in
        the point must equal the Profile set present in the source
        tree (see below), so a zero-Profile or subset point cannot
        stand in for a source it does not cover."""
        source_root = Path(self.plan.source_data_root)
        problems: list[str] = []
        for profile in manifest.get("profiles") or []:
            rel_dir = profile.get("dir")
            if not rel_dir:
                continue
            for rel, meta in (profile.get("files") or {}).items():
                if "link" in meta:
                    continue
                path = source_root / rel_dir / rel
                if not path.is_file():
                    problems.append(f"{rel_dir}/{rel}: missing from source tree")
                elif path.stat().st_size != meta.get("size") or _sha256_file(
                    path
                ) != meta.get("sha256"):
                    problems.append(
                        f"{rel_dir}/{rel}: differs from the restore point"
                    )
                if len(problems) >= 20:
                    break
        if problems:
            raise MigrationError(
                "restore point does not belong to this source tree: "
                + "; ".join(problems[:20])
            )
        # Bidirectional coverage (t080 f011): anchoring only proves the
        # point's files exist in the source.  The Profile SETS must also
        # be equal — a point that records no Profile, or only a subset,
        # leaves source Profiles without a restorable backup and must
        # refuse the switch just like a foreign point.
        source_profiles: set[str] = set()
        for record in self.plan.records:
            parts = record.source_rel.split("/")
            if record.source_root == "data" and len(parts) >= 2 and parts[0] == "profiles":
                source_profiles.add(parts[1])
        for d in self.plan.dirs:
            parts = d.source_rel.split("/")
            if d.source_root == "data" and len(parts) >= 2 and parts[0] == "profiles":
                source_profiles.add(parts[1])
        manifest_profiles: set[str] = set()
        for profile in manifest.get("profiles") or []:
            rel_dir = profile.get("dir")
            if rel_dir:
                parts = str(rel_dir).split("/")
                if len(parts) >= 2 and parts[0] == "profiles":
                    manifest_profiles.add(parts[1])
        if source_profiles != manifest_profiles:
            missing = sorted(source_profiles - manifest_profiles)
            extra = sorted(manifest_profiles - source_profiles)
            raise MigrationError(
                "restore point Profile coverage does not match the "
                f"source tree: not covered: {missing or '[]'}; "
                f"not in source: {extra or '[]'}"
            )

    def _check_writers(self) -> None:
        detector = self.writer_detector or detect_writers
        roots = [
            Path(self.plan.source_data_root),
            Path(self.plan.source_fonts_dir),
        ]
        offenders = detector(roots)
        if offenders is None:
            if not self.confirm_stack_stopped:
                raise MigrationError(
                    "writer detection unavailable (lsof missing); re-run with "
                    "the stack stopped and --i-confirm-stack-stopped"
                )
            return
        if offenders:
            raise WriterActiveError(
                "source files are held open by: " + ", ".join(offenders[:10])
            )

    def _check_capacity(self) -> None:
        needed: dict[str, int] = {}
        for record in self.plan.records:
            needed[record.target_kind] = needed.get(record.target_kind, 0) + record.size
        for kind, bytes_needed in needed.items():
            target = self.targets[kind]
            target.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(target).free
            if free < bytes_needed:
                raise MigrationError(
                    f"target volume {kind} has {free} bytes free, "
                    f"migration needs {bytes_needed}"
                )

    def _source_path(self, record: FileRecord) -> Path:
        base = (
            Path(self.plan.source_data_root)
            if record.source_root == "data"
            else Path(self.plan.source_fonts_dir)
        )
        return base / record.source_rel

    def _copy_file(self, source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        shutil.copymode(source, destination)

    def _stage(self) -> None:
        for record in self.plan.records:
            staged = (
                self._staging_dir(record.target_kind) / record.target_rel
            )
            if staged.is_file() and _sha256_file(staged) == record.sha256:
                continue
            self._copy_file(self._source_path(record), staged)

    def _verify_staging(self) -> None:
        problems: list[str] = []
        for record in self.plan.records:
            staged = self._staging_dir(record.target_kind) / record.target_rel
            if not staged.is_file():
                problems.append(f"{record.target_kind}:{record.target_rel} missing")
            elif _sha256_file(staged) != record.sha256:
                problems.append(
                    f"{record.target_kind}:{record.target_rel} digest mismatch"
                )
            if len(problems) >= 20:
                break
        if problems:
            raise MigrationError("staging verification failed: " + "; ".join(problems))

    def _switch(self) -> None:
        # Directories first (shallow to deep) so file renames land in
        # existing parents; modes are applied after all files are in
        # place, deepest first, so a restrictive parent mode cannot
        # block a child (t080 f006: empty directories and directory
        # permissions are part of the migrated structure).
        placed_dirs: list[dict] = list(self._journal.get("placed_dirs", []))
        placed_dir_keys = {(d["kind"], d["rel"]) for d in placed_dirs}
        for d in sorted(
            self.plan.dirs, key=lambda d: (d.target_rel.count("/"), d.target_rel)
        ):
            key = (d.target_kind, d.target_rel)
            destination = self.targets[d.target_kind] / d.target_rel
            existed = destination.is_dir()
            destination.mkdir(parents=True, exist_ok=True)
            if not existed and key not in placed_dir_keys:
                placed_dirs.append(
                    {"kind": d.target_kind, "rel": d.target_rel, "mode": d.mode}
                )
                placed_dir_keys.add(key)
        self._journal["placed_dirs"] = placed_dirs
        # Persist the directory placements before any file work (t080
        # f008): if the first file placement is refused, rollback must
        # still know which directories this run created.
        self._save_journal("verified")
        placed: list[dict] = list(self._journal.get("placed", []))
        placed_keys = {(p["kind"], p["rel"]) for p in placed}
        for record in self.plan.records:
            key = (record.target_kind, record.target_rel)
            destination = self.targets[record.target_kind] / record.target_rel
            if key in placed_keys:
                continue
            if destination.is_file():
                if _sha256_file(destination) == record.sha256:
                    placed.append(
                        {
                            "kind": record.target_kind,
                            "rel": record.target_rel,
                            "sha256": record.sha256,
                            "adopted": True,
                        }
                    )
                    placed_keys.add(key)
                    continue
                raise MigrationError(
                    f"target {record.target_kind}:{record.target_rel} already "
                    "exists with different content; refusing to overwrite"
                )
            staged = self._staging_dir(record.target_kind) / record.target_rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(destination)
            placed.append(
                {
                    "kind": record.target_kind,
                    "rel": record.target_rel,
                    "sha256": record.sha256,
                    "adopted": False,
                }
            )
            placed_keys.add(key)
            self._journal["placed"] = placed
            self._save_journal("verified")
        self._journal["placed"] = placed
        for d in sorted(
            self.plan.dirs,
            key=lambda d: (-d.target_rel.count("/"), d.target_rel),
        ):
            destination = self.targets[d.target_kind] / d.target_rel
            if destination.is_dir():
                os.chmod(destination, d.mode)

    def rollback(self) -> str:
        """Remove exactly what this migration placed; source stays untouched."""
        self._load_journal()
        if not self._journal:
            raise MigrationError("no migration journal to roll back")
        # Adopt the journal's identity (t080 f004): a rollback runner
        # built from an empty plan (the CLI path) must locate the
        # original run's staging trees and must not rewrite the
        # journal's identity fields with its own derived values.
        if self._journal.get("run_id"):
            self.run_id = str(self._journal["run_id"])
        problems: list[str] = []
        for entry in self._journal.get("placed", []):
            if entry.get("adopted"):
                continue
            path = self.targets[entry["kind"]] / entry["rel"]
            if not path.is_file():
                continue
            if _sha256_file(path) != entry["sha256"]:
                problems.append(
                    f"{entry['kind']}:{entry['rel']} changed since placement"
                )
                continue
            path.unlink()
        if problems:
            raise MigrationError(
                "rollback refused, placed files changed: " + "; ".join(problems)
            )
        for entry in sorted(
            self._journal.get("placed_dirs", []),
            key=lambda d: -str(d["rel"]).count("/"),
        ):
            path = self.targets[entry["kind"]] / entry["rel"]
            try:
                path.rmdir()  # only succeeds while empty
            except OSError:
                pass
        for kind in self.targets:
            shutil.rmtree(self._staging_dir(kind), ignore_errors=True)
        self._save_journal("rolled_back")
        return "rolled_back"
