"""Per-instance Selkies credential files never reuse a path across restarts."""

from __future__ import annotations

import json
from pathlib import Path

from cbrowser.supervisor.selkies_tokens import SelkiesTokens


def test_each_instance_gets_a_fresh_credentials_path_and_stale_ones_are_removed(
    tmp_path: Path,
) -> None:
    secret_dir = tmp_path / "secrets" / "p1"
    secret_dir.mkdir(parents=True)

    first = SelkiesTokens.generate().provision_credentials_file(secret_dir, "inst_a")
    second_tokens = SelkiesTokens.generate()
    second = second_tokens.provision_credentials_file(secret_dir, "inst_b")

    # A restart must not atomically replace a path a previous Stream container
    # bind-mounted: some Docker file-sharing layers then expose a stale entry.
    assert first != second
    assert not first.exists()
    assert sorted(p.name for p in secret_dir.iterdir()) == [second.name]
    assert (second.stat().st_mode & 0o777) == 0o600
    data = json.loads(second.read_text(encoding="utf-8"))
    assert data["controller_token"] == second_tokens.controller_token


def test_provision_rejects_instance_ids_that_escape_the_directory(
    tmp_path: Path,
) -> None:
    secret_dir = tmp_path / "secrets" / "p1"
    secret_dir.mkdir(parents=True)
    tokens = SelkiesTokens.generate()
    for bad in ("", "../x", "a/b", "a\\b"):
        try:
            tokens.provision_credentials_file(secret_dir, bad)
        except ValueError:
            continue
        raise AssertionError(f"instance id {bad!r} was accepted")
    assert list(secret_dir.iterdir()) == []
