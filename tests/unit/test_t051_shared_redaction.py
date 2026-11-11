"""t051 A58/AC-020: one shared redaction rule set for evidence logs and
Supervisor Docker errors.

The rules live in ``cbrowser.redact``; ``scripts/redact_evidence.py`` and
the Supervisor Docker error paths both delegate to it, so a credential
shape fixed in one place is fixed in both.  The matrix below is the
contract: every row must come out with the secret gone and a placeholder
in its place, while ordinary text survives.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from cbrowser.redact import docker_error_detail, redact

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "raw, leaked, kept",
    [
        # URL userinfo: proxy URLs are the live credential shape in logs.
        (
            "dial tcp: http://proxy-user:s3cret@proxy.example:8080/x",
            ["proxy-user", "s3cret"],
            ["http://<redacted>@proxy.example:8080/x"],
        ),
        (
            "GET http://only-user@internal:9000/ failed",
            ["only-user"],
            ["http://<redacted>@internal:9000/"],
        ),
        (
            "plain https://example.com/no-credentials/path stays",
            [],
            ["https://example.com/no-credentials/path"],
        ),
        # Bearer tokens.
        (
            "Authorization: Bearer abc.def-123",
            ["abc.def-123"],
            ["Authorization: Bearer <redacted>"],
        ),
        # Lowercase schemes: HTTP auth schemes are case-insensitive, so
        # a lowercase `bearer`/`basic` must redact exactly like the
        # capitalised form (t051 review f003).
        (
            "authorization: bearer abc.def-123",
            ["abc.def-123"],
            ["authorization: bearer <redacted>"],
        ),
        (
            "Authorization: Basic dXNlcjpwYXNz",
            ["dXNlcjpwYXNz"],
            ["Authorization: Basic <redacted>"],
        ),
        (
            "authorization: basic dXNlcjpwYXNz",
            ["dXNlcjpwYXNz"],
            ["authorization: basic <redacted>"],
        ),
        # Any cookie value, not just the session cookie name.
        (
            "Cookie: theme=dark; session_token=xyz-secret; lang=en",
            ["xyz-secret"],
            ["theme=<redacted>", "session_token=<redacted>", "lang=<redacted>"],
        ),
        (
            "Set-Cookie: cbrowser_session=abc123; Path=/; HttpOnly",
            ["abc123"],
            ["cbrowser_session=<redacted>", "Path=/"],
        ),
        (
            "Set-Cookie: pref=zz; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/",
            ["zz"],
            ["pref=<redacted>", "Expires=Wed, 21 Oct 2026 07:28:00 GMT"],
        ),
        # Bare session cookie name anywhere (pre-t051 evidence behaviour).
        (
            "cbrowser_session=sessvalue; other",
            ["sessvalue"],
            ["cbrowser_session=<redacted>"],
        ),
        # Sensitive key with a quoted value containing spaces: the whole
        # quoted value goes, not just the first word (A58).
        (
            '"password": "my secret phrase"',
            ["my secret phrase"],
            ['"password": "<redacted>"'],
        ),
        (
            "{'api_key': 'sk live key with spaces'}",
            ["sk live key with spaces"],
            ["'api_key': '<redacted>'"],
        ),
        # Sensitive key, unquoted value.
        (
            "login password=hunter2",
            ["hunter2"],
            ["login password=<redacted>"],
        ),
        (
            '"token": "abc123", cbrowser_session=sessvalue; other',
            ["abc123", "sessvalue"],
            ['"token": "<redacted>"', "cbrowser_session=<redacted>"],
        ),
        # Home directory paths.
        (
            "open /Users/karson/kar/code/CBrowser/data/fonts failed",
            ["/Users/karson"],
            ["<home>/kar/code/CBrowser/data/fonts"],
        ),
        (
            "open /home/karson/data/cbrowser.db failed",
            ["/home/karson"],
            ["<home>/data/cbrowser.db"],
        ),
        # Plain text is untouched.
        (
            "plain line stays\n",
            [],
            ["plain line stays"],
        ),
    ],
)
def test_shared_redaction_matrix(raw: str, leaked: list[str], kept: list[str]) -> None:
    out = redact(raw)
    for secret in leaked:
        assert secret not in out, f"leaked {secret!r} in {out!r}"
    for fragment in kept:
        assert fragment in out, f"missing {fragment!r} in {out!r}"


def test_redact_is_idempotent_on_placeholders() -> None:
    sample = (
        "Authorization: Bearer <redacted>\n"
        '"token": "<redacted>", cbrowser_session=<redacted>\n'
    )
    assert redact(sample) == sample


def test_docker_error_detail_redacts_and_falls_back_to_type() -> None:
    exc = RuntimeError(
        "400 Client Error: proxy http://proxy-user:s3cret@proxy:8080 refused"
    )
    detail = docker_error_detail(exc)
    assert "proxy-user" not in detail
    assert "s3cret" not in detail
    assert "http://<redacted>@proxy:8080" in detail
    assert docker_error_detail(RuntimeError()) == "RuntimeError"


def test_redact_evidence_script_delegates_to_shared_rules() -> None:
    sample = (
        "proxy http://proxy-user:s3cret@proxy.example:8080/x\n"
        "Cookie: theme=dark; session_token=xyz-secret\n"
        '"password": "my secret phrase"\n'
        "open /Users/karson/data/cbrowser.db failed\n"
        "plain line stays\n"
    )
    result = subprocess.run(
        [sys.executable, "scripts/redact_evidence.py"],
        cwd=ROOT,
        input=sample,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,  # the test asserts on returncode/output
    )
    assert result.returncode == 0, result.stderr
    for secret in ("proxy-user", "s3cret", "xyz-secret", "my secret phrase", "/Users/karson"):
        assert secret not in result.stdout, secret
    assert "plain line stays" in result.stdout
    assert result.stdout.count("<redacted>") == 4  # URL userinfo collapses two secrets into one marker
