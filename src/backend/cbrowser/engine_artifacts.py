"""Pinned approved CloakBrowser engine artifacts, integrity checks, and anti-bypass guards.

ADR 021 pins ``cloakbrowser[geoip]==0.6.4``. Upstream CloakBrowser releases sign
only the downloadable archive manifest (``SHA256SUMS`` + detached Ed25519
``SHA256SUMS.sig`` verified against ``BINARY_SIGNING_PUBKEYS`` in the wrapper);
once extracted into ``engine-cache``, upstream leaves no per-file manifest or
signature and ``ensure_binary()`` trusts any existing executable ``chrome``.

This module is the single source of truth for CBrowser's approved engine
artifacts and integrity enforcement across ``deploy.sh``, Supervisor ``cache_init``,
and ``BrowserRunner``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

CLOAKBROWSER_PACKAGE_VERSION = "0.6.4"

# Ed25519 raw 32-byte public keys (base64) embedded in cloakbrowser==0.6.4.
UPSTREAM_SIGNING_PUBKEYS: tuple[str, ...] = (
    "MKFKwIhUcKWq5xTuNA0Ovg99njcDEcEJvmWYYhApvaU=",
)

TRUST_SOURCE_ARM64 = (
    "Ed25519 detached signature (SHA256SUMS.sig) verified against "
    "cloakbrowser==0.6.4 BINARY_SIGNING_PUBKEYS for archive download + "
    "CBrowser repository SHA-256 manifest for extracted runtime files"
)

TRUST_SOURCE_X64_ARCHIVE_ONLY = (
    "Ed25519 detached signature (SHA256SUMS.sig) verified against "
    "cloakbrowser==0.6.4 BINARY_SIGNING_PUBKEYS for archive download; "
    "extracted runtime file digests unverified on arm64 host"
)

INTEGRITY_MECHANISM_PINNED = (
    "upstream_ed25519_signed_tarball_manifest + cbrowser_pinned_extracted_sha256"
)

DEFAULT_APPROVED_BUILD_BY_PLATFORM: dict[str, str] = {
    "linux-arm64": "146.0.7680.177.3",
    "linux-x64": "146.0.7680.177.5",
}

_AUTO_UPDATE_MARKER_PATTERNS = (
    "latest_version",
    "latest_version_*",
    "latest_pro_version*",
)


class EngineArtifactError(RuntimeError):
    """Fail-closed engine artifact pinning or integrity verification error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ApprovedEngineArtifact:
    platform_tag: str
    engine_build: str
    chromium_version: str
    elf_machine: int
    archive_name: str
    archive_sha256: str
    binary_sha256: str | None
    file_sha256s: dict[str, str]
    integrity_mechanism: str
    trust_source: str
    signing_pubkeys: tuple[str, ...]

    def to_metadata_dict(self) -> dict[str, Any]:
        return {
            "cloakbrowser_package": CLOAKBROWSER_PACKAGE_VERSION,
            "platform_tag": self.platform_tag,
            "engine_build": self.engine_build,
            "chromium_version": self.chromium_version,
            "archive_name": self.archive_name,
            "archive_sha256": self.archive_sha256,
            "binary_sha256": self.binary_sha256,
            "pinned_file_count": len(self.file_sha256s),
            "integrity_mechanism": self.integrity_mechanism,
            "trust_source": self.trust_source,
            "signing_pubkeys": list(self.signing_pubkeys),
            "auto_update_disabled": True,
        }


@dataclass(frozen=True)
class EngineVerificationResult:
    platform_tag: str
    engine_build: str
    chromium_version: str
    binary_path: str
    binary_sha256: str
    archive_sha256: str
    verified_files_count: int
    integrity_mechanism: str
    trust_source: str
    cloakbrowser_package: str = CLOAKBROWSER_PACKAGE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_tag": self.platform_tag,
            "engine_build": self.engine_build,
            "chromium_version": self.chromium_version,
            "binary_path": self.binary_path,
            "binary_sha256": self.binary_sha256,
            "archive_sha256": self.archive_sha256,
            "verified_files_count": self.verified_files_count,
            "integrity_mechanism": self.integrity_mechanism,
            "trust_source": self.trust_source,
            "cloakbrowser_package": self.cloakbrowser_package,
            "approved": True,
        }


_ARM64_146_3_FILES: dict[str, str] = {
    "chrome": "3cf5231598c4fd44be1ed10c58cab4a1d59cd18b05a4800c73b946e0bfc4d34f",
    "chrome_100_percent.pak": "4036ff99b6256c3755339c65f5a7c2145e64177d68174fe239c03c993b5f0873",
    "chrome_200_percent.pak": "75102c95f291b40420978296ad6422da9629cf4dc52a6bd2dc73c2c701bae864",
    "chrome_crashpad_handler": "5df6dbc06a959650e23e8c95714debe575570a5e110efd540296a52cb205b3c5",
    "chromedriver": "39688ada8707333eb04e574740fff46d120d3f5b1ef5ccfdff6bbe5843ad306b",
    "headless_command_resources.pak": "4b42577e8d7a7a20072b002b38742176f7531e6d7cc1f37787db70317e2afd69",
    "icudtl.dat": "1cf67874b5a87a8363a86fb3f81e3cbbed54d389062dab8fb52308d5cf8c8612",
    "libEGL.so": "5a0cf95b2159c73ad7eba9764fcf27fca6ce78c188ece17daee938b87f499846",
    "libGLESv2.so": "999d6079e75419ed36d2d68c473240d200772f597d9eb92bede7d4e5100a233d",
    "libvk_swiftshader.so": "281538615a270f19732e693f1aba144aaef1006cda162890350aa9153b0439ad",
    "libvulkan.so.1": "3803584ba37d5cc1839d825cc8aa0182da62953d4aa63bbc077bf2928f798f5a",
    "resources.pak": "425d4e94011955308d8b7e2b693aef974ac16cd494b44d77a6645ede2cff03b0",
    "snapshot_blob.bin": "794a6d201d8ef5e8fad648e291055c535cd017bc87f8b036c6675f4c905137a9",
    "v8_context_snapshot.bin": "a02f07b98ccb6bc25854ec32c2eb0d96a2b487a4015e47b2abb7f10675cd5592",
    "vk_swiftshader_icd.json": "c9eef28b6b984fec220ef0abfecc40b502d46946706e47bfe97707027cb818bd",
}

APPROVED_ENGINE_ARTIFACTS: dict[tuple[str, str], ApprovedEngineArtifact] = {
    ("linux-arm64", "146.0.7680.177.3"): ApprovedEngineArtifact(
        platform_tag="linux-arm64",
        engine_build="146.0.7680.177.3",
        chromium_version="146.0.7680.177",
        elf_machine=183,
        archive_name="cloakbrowser-linux-arm64.tar.gz",
        archive_sha256="8b71ce53b4fd131327331a31fba3835d71882d19bfaabde78dd0f5390bd16f45",
        binary_sha256=_ARM64_146_3_FILES["chrome"],
        file_sha256s=dict(_ARM64_146_3_FILES),
        integrity_mechanism=INTEGRITY_MECHANISM_PINNED,
        trust_source=TRUST_SOURCE_ARM64,
        signing_pubkeys=UPSTREAM_SIGNING_PUBKEYS,
    ),
    ("linux-x64", "146.0.7680.177.5"): ApprovedEngineArtifact(
        platform_tag="linux-x64",
        engine_build="146.0.7680.177.5",
        chromium_version="146.0.7680.177",
        elf_machine=62,
        archive_name="cloakbrowser-linux-x64.tar.gz",
        archive_sha256="4a12bcde95fa1bb1beef2b41ab5e5c27c36be78e3be3d0dac8c64d705216670e",
        binary_sha256=None,
        file_sha256s={},
        integrity_mechanism="upstream_ed25519_signed_tarball_manifest",
        trust_source=TRUST_SOURCE_X64_ARCHIVE_ONLY,
        signing_pubkeys=UPSTREAM_SIGNING_PUBKEYS,
    ),
}


def current_linux_platform_tag(machine: str | None = None) -> str:
    arch = (machine or platform.machine()).lower()
    if arch in ("arm64", "aarch64"):
        return "linux-arm64"
    if arch in ("x86_64", "amd64"):
        return "linux-x64"
    raise EngineArtifactError(
        "unsupported_architecture",
        f"Unsupported runtime engine architecture: {arch!r}",
    )


def get_approved_artifact(
    platform_tag: str | None = None,
    engine_build: str | None = None,
    *,
    registry: Mapping[tuple[str, str], ApprovedEngineArtifact] | None = None,
) -> ApprovedEngineArtifact:
    tag = platform_tag or current_linux_platform_tag()
    build = engine_build or DEFAULT_APPROVED_BUILD_BY_PLATFORM.get(tag)
    if not build:
        raise EngineArtifactError(
            "unapproved_engine_build",
            f"No approved engine build registered for platform {tag!r}",
        )
    table = APPROVED_ENGINE_ARTIFACTS if registry is None else registry
    artifact = table.get((tag, build))
    if artifact is None:
        raise EngineArtifactError(
            "unapproved_engine_build",
            f"Engine build {build!r} for {tag!r} is not in the approved ADR 021 manifest",
        )
    return artifact


def check_forbidden_engine_env(
    env: Mapping[str, str] | None = None,
    *,
    expected_build: str | None = None,
    expected_binary_sha256: str | None = None,
    allow_binary_override: bool = False,
) -> list[str]:
    """Return human-readable problems for any env var attempting bypass/auto-update."""
    source = os.environ if env is None else env
    problems: list[str] = []

    auto_update = source.get("CLOAKBROWSER_AUTO_UPDATE")
    if auto_update is not None and auto_update.strip() != "":
        if auto_update.strip().lower() != "false":
            problems.append(
                f"CLOAKBROWSER_AUTO_UPDATE={auto_update!r} is forbidden (auto-update bypass; must be 'false' or unset)"
            )

    for var in (
        "CLOAKBROWSER_DOWNLOAD_URL",
        "CLOAKBROWSER_SKIP_CHECKSUM",
        "CLOAKBROWSER_LICENSE_KEY",
    ):
        val = source.get(var)
        if val is not None and val.strip() != "":
            problems.append(
                f"{var} is forbidden under pinned ADR 021 artifact verification (bypass attempt)"
            )

    if not allow_binary_override:
        override = source.get("CLOAKBROWSER_BINARY_PATH")
        if override is not None and override.strip() != "":
            problems.append(
                "CLOAKBROWSER_BINARY_PATH override is forbidden during engine verification"
            )

    if expected_build:
        pinned_ver = source.get("CLOAKBROWSER_VERSION")
        if pinned_ver is not None and pinned_ver.strip() != "" and pinned_ver.strip() != expected_build:
            problems.append(
                f"CLOAKBROWSER_VERSION={pinned_ver.strip()!r} conflicts with pinned build {expected_build!r}"
            )
        env_build = source.get("CBROWSER_ENGINE_BUILD")
        if env_build is not None and env_build.strip() != "" and env_build.strip() != expected_build:
            problems.append(
                f"CBROWSER_ENGINE_BUILD={env_build.strip()!r} conflicts with pinned build {expected_build!r}"
            )

    if expected_binary_sha256:
        env_sha = source.get("CBROWSER_ENGINE_BINARY_SHA256")
        if (
            env_sha is not None
            and env_sha.strip() != ""
            and env_sha.strip().lower() != expected_binary_sha256.lower()
        ):
            problems.append(
                "CBROWSER_ENGINE_BINARY_SHA256 conflicts with approved manifest digest"
            )

    return problems


def enforce_pinned_engine_env(
    env: Mapping[str, str] | None = None,
    *,
    expected_build: str | None = None,
    expected_binary_sha256: str | None = None,
    allow_binary_override: bool = False,
) -> None:
    problems = check_forbidden_engine_env(
        env,
        expected_build=expected_build,
        expected_binary_sha256=expected_binary_sha256,
        allow_binary_override=allow_binary_override,
    )
    if problems:
        raise EngineArtifactError("auto_update_bypass_env", "; ".join(problems))


def detect_auto_update_markers(cache_dir: Path) -> list[str]:
    """Find auto-update marker files that can hijack unpinned CloakBrowser launches."""
    if not cache_dir.is_dir():
        return []
    found: list[str] = []
    for pattern in _AUTO_UPDATE_MARKER_PATTERNS:
        for path in sorted(cache_dir.glob(pattern)):
            if path.name not in found:
                found.append(path.name)
    return found


def verify_wrapper_package(
    expected_version: str = CLOAKBROWSER_PACKAGE_VERSION,
) -> dict[str, Any]:
    """Verify the installed cloakbrowser wrapper matches the ADR 021 locked release."""
    import cloakbrowser
    from cloakbrowser.config import BINARY_SIGNING_PUBKEYS, PLATFORM_CHROMIUM_VERSIONS

    actual_version = getattr(cloakbrowser, "__version__", None)
    if actual_version != expected_version:
        raise EngineArtifactError(
            "wrapper_version_mismatch",
            f"Expected cloakbrowser=={expected_version}, got {actual_version!r}",
        )
    for tag, expected_build in DEFAULT_APPROVED_BUILD_BY_PLATFORM.items():
        actual_build = PLATFORM_CHROMIUM_VERSIONS.get(tag)
        if actual_build != expected_build:
            raise EngineArtifactError(
                "wrapper_platform_version_mismatch",
                f"cloakbrowser PLATFORM_CHROMIUM_VERSIONS[{tag!r}]={actual_build!r}, expected {expected_build!r}",
            )
    if not any(k in BINARY_SIGNING_PUBKEYS for k in UPSTREAM_SIGNING_PUBKEYS):
        raise EngineArtifactError(
            "wrapper_signing_key_mismatch",
            "Expected Ed25519 signing key missing from cloakbrowser.config.BINARY_SIGNING_PUBKEYS",
        )
    return {
        "version": actual_version,
        "platform_versions": dict(PLATFORM_CHROMIUM_VERSIONS),
        "signing_pubkeys": list(BINARY_SIGNING_PUBKEYS),
    }


def _sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_extracted_engine_cache(
    cache_dir: Path,
    *,
    platform_tag: str | None = None,
    engine_build: str | None = None,
    run_version_probe: bool = True,
    registry: Mapping[tuple[str, str], ApprovedEngineArtifact] | None = None,
) -> EngineVerificationResult:
    """Strictly verify an extracted engine-cache directory against approved digests."""
    artifact = get_approved_artifact(platform_tag, engine_build, registry=registry)
    markers = detect_auto_update_markers(cache_dir)
    if markers:
        raise EngineArtifactError(
            "auto_update_marker_present",
            f"Forbidden CloakBrowser auto-update marker(s) present: {', '.join(markers)}",
        )
    if not artifact.binary_sha256:
        raise EngineArtifactError(
            "missing_pinned_digest",
            f"No extracted binary SHA-256 pinned for {artifact.platform_tag}/{artifact.engine_build}",
        )

    try:
        resolved_cache = cache_dir.resolve(strict=True)
    except OSError:
        raise EngineArtifactError(
            "missing_engine_binary",
            f"Engine cache directory does not exist: {cache_dir}",
        ) from None

    # Reject any unapproved sibling chromium-* directories in the cache
    for child in sorted(resolved_cache.iterdir()):
        if child.is_dir() and child.name.startswith("chromium-"):
            sibling_build = child.name.removeprefix("chromium-")
            if sibling_build != artifact.engine_build:
                raise EngineArtifactError(
                    "unapproved_engine_build",
                    f"Unapproved engine directory present in cache: {child.name}",
                )

    build_dir_raw = resolved_cache / f"chromium-{artifact.engine_build}"
    try:
        build_dir = build_dir_raw.resolve(strict=True)
        build_dir.relative_to(resolved_cache)
    except (OSError, ValueError):
        raise EngineArtifactError(
            "missing_engine_binary",
            f"Missing or invalid engine build directory: {build_dir_raw}",
        ) from None
    if build_dir.name != f"chromium-{artifact.engine_build}":
        raise EngineArtifactError(
            "missing_engine_binary",
            f"Unexpected engine build directory target: {build_dir}",
        )

    candidate = build_dir / "chrome"
    if candidate.is_symlink():
        raise EngineArtifactError(
            "corrupted_engine_binary",
            "Engine binary must be a regular file, not a symlink",
        )
    try:
        binary = candidate.resolve(strict=True)
        binary.relative_to(build_dir)
    except (OSError, ValueError):
        raise EngineArtifactError(
            "missing_engine_binary",
            f"Engine binary missing or escaped cache: {candidate}",
        ) from None

    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise EngineArtifactError(
            "missing_engine_binary",
            f"Engine binary is missing or not executable: {binary}",
        )

    with binary.open("rb") as source:
        header = source.read(64)
    if (
        len(header) < 64
        or header[:7] != b"\x7fELF\x02\x01\x01"
        or int.from_bytes(header[18:20], "little") != artifact.elf_machine
    ):
        raise EngineArtifactError(
            "elf_architecture_mismatch",
            f"Engine ELF header/machine mismatch for {artifact.platform_tag} (expected {artifact.elf_machine})",
        )

    actual_chrome_sha = _sha256_file(binary)
    if actual_chrome_sha != artifact.binary_sha256:
        raise EngineArtifactError(
            "corrupted_engine_binary",
            f"Engine chrome SHA-256 mismatch: expected {artifact.binary_sha256}, got {actual_chrome_sha}",
        )

    verified_count = 0
    expected_files = dict(artifact.file_sha256s)
    if "chrome" not in expected_files:
        expected_files["chrome"] = artifact.binary_sha256
    for rel_name, expected_sha in sorted(expected_files.items()):
        target_path = build_dir / rel_name
        if target_path.is_symlink():
            raise EngineArtifactError(
                "corrupted_engine_file",
                f"Engine runtime file must not be a symlink: {rel_name}",
            )
        try:
            resolved_file = target_path.resolve(strict=True)
            resolved_file.relative_to(build_dir)
        except (OSError, ValueError):
            raise EngineArtifactError(
                "corrupted_engine_file",
                f"Required engine runtime file missing: {rel_name}",
            ) from None
        if not resolved_file.is_file():
            raise EngineArtifactError(
                "corrupted_engine_file",
                f"Required engine runtime file is not a regular file: {rel_name}",
            )
        actual_sha = _sha256_file(resolved_file)
        if actual_sha != expected_sha:
            raise EngineArtifactError(
                "corrupted_engine_file",
                f"Engine runtime file SHA-256 mismatch for {rel_name}: expected {expected_sha}, got {actual_sha}",
            )
        verified_count += 1

    if run_version_probe:
        try:
            result = subprocess.run(
                [str(binary), "--version"],
                env=dict(os.environ),
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise EngineArtifactError(
                "version_probe_mismatch",
                f"Engine --version execution failed: {type(exc).__name__}",
            ) from None
        if artifact.chromium_version not in re.findall(
            r"\b\d+\.\d+\.\d+\.\d+\b", result.stdout
        ):
            raise EngineArtifactError(
                "version_probe_mismatch",
                f"Engine --version output {result.stdout.strip()!r} does not match {artifact.chromium_version!r}",
            )

    return EngineVerificationResult(
        platform_tag=artifact.platform_tag,
        engine_build=artifact.engine_build,
        chromium_version=artifact.chromium_version,
        binary_path=str(binary),
        binary_sha256=actual_chrome_sha,
        archive_sha256=artifact.archive_sha256,
        verified_files_count=verified_count,
        integrity_mechanism=artifact.integrity_mechanism,
        trust_source=artifact.trust_source,
    )


def _shell_assign(name: str, value: str) -> str:
    quoted = "'" + value.replace("'", "'\"'\"'") + "'"
    return f"{name}={quoted}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify and resolve pinned ADR 021 CloakBrowser engine artifacts"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    describe_p = sub.add_parser("describe", help="Print pinned engine metadata")
    describe_p.add_argument("--platform", default=None)
    describe_p.add_argument("--build", default=None)
    describe_p.add_argument("--shell", action="store_true")

    verify_p = sub.add_parser("verify-cache", help="Verify engine cache directory")
    verify_p.add_argument("--cache-dir", required=True)
    verify_p.add_argument("--platform", default=None)
    verify_p.add_argument("--build", default=None)
    verify_p.add_argument("--allow-empty", action="store_true")
    verify_p.add_argument("--no-version-probe", action="store_true")

    args = parser.parse_args(argv)
    try:
        artifact = get_approved_artifact(args.platform, args.build)
        enforce_pinned_engine_env(
            os.environ,
            expected_build=artifact.engine_build,
            expected_binary_sha256=artifact.binary_sha256,
            allow_binary_override=False,
        )
        if args.command == "describe":
            if args.shell:
                lines = [
                    _shell_assign("CBROWSER_ENGINE_PLATFORM", artifact.platform_tag),
                    _shell_assign("CBROWSER_ENGINE_BUILD", artifact.engine_build),
                    _shell_assign("CBROWSER_ENGINE_VERSION", artifact.engine_build),
                    _shell_assign("CBROWSER_ENGINE_ARCHIVE_SHA256", artifact.archive_sha256),
                    _shell_assign(
                        "CBROWSER_ENGINE_BINARY_SHA256",
                        artifact.binary_sha256 or "",
                    ),
                    _shell_assign(
                        "CBROWSER_ENGINE_INTEGRITY_MECHANISM",
                        artifact.integrity_mechanism,
                    ),
                    _shell_assign("CBROWSER_ENGINE_TRUST_SOURCE", artifact.trust_source),
                    _shell_assign("CBROWSER_CLOAKBROWSER_PACKAGE", CLOAKBROWSER_PACKAGE_VERSION),
                    _shell_assign("CLOAKBROWSER_AUTO_UPDATE", "false"),
                ]
                print("\n".join(lines))
            else:
                print(json.dumps(artifact.to_metadata_dict(), indent=2))
            return 0

        cache_dir = Path(args.cache_dir)
        markers = detect_auto_update_markers(cache_dir)
        if markers:
            raise EngineArtifactError(
                "auto_update_marker_present",
                f"Forbidden CloakBrowser auto-update marker(s) present: {', '.join(markers)}",
            )
        chromium_dirs = (
            [p for p in cache_dir.iterdir() if p.is_dir() and p.name.startswith("chromium-")]
            if cache_dir.is_dir()
            else []
        )
        if not chromium_dirs and args.allow_empty:
            print(
                json.dumps(
                    {
                        "status": "deferred_to_cache_init",
                        "artifact": artifact.to_metadata_dict(),
                    }
                )
            )
            return 0

        result = verify_extracted_engine_cache(
            cache_dir,
            platform_tag=artifact.platform_tag,
            engine_build=artifact.engine_build,
            run_version_probe=not args.no_version_probe,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    except EngineArtifactError as exc:
        print(f"Engine artifact verification failed ({exc.code}): {exc.detail}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
