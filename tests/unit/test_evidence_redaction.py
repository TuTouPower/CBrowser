"""Evidence artifacts never persist secret values."""

from pathlib import Path

from gateway_probe.evidence import save_evidence


def test_saved_evidence_redacts_secrets_and_payloads(tmp_path: Path) -> None:
    path = save_evidence(
        "redaction",
        {
            "token": "super-secret-token",
            "nested": {"password": "hunter2", "note": "visible"},
            "payload": "abcdef",
        },
        target_dir=tmp_path,
    )
    text = path.read_text(encoding="utf-8")
    assert "super-secret-token" not in text
    assert "hunter2" not in text
    assert "abcdef" not in text
    assert "<redacted>" in text
    assert "<redacted:6 bytes>" in text
    assert "visible" in text
