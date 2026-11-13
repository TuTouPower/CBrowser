"""t066: deploy.sh exposes the environment restore point as subcommands.

Source-level wiring contract (same style as the other deploy.sh source
tests): env-backup / env-restore dispatch to scripts/restore_point.py
in a throwaway API container with the named database volume and the
data root mounted, and env-restore stops the stack first.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "deploy.sh"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_env_subcommands_are_dispatched():
    text = _text()
    assert "env-backup) cmd_env_backup" in text
    assert "env-restore) cmd_env_restore" in text


def test_env_backup_runs_restore_point_create_with_volume_and_data_root():
    text = _text()
    backup_section = text.split("cmd_env_backup()")[1].split("cmd_env_restore()")[0]
    assert "restore_point.py create" in backup_section
    assert '-v "$(db_volume_name):/db"' in backup_section
    assert '-v "$DATA_ROOT:/data"' in backup_section
    assert "--secrets-dir /secrets" in backup_section


def test_env_restore_stops_stack_and_runs_restore_point_restore():
    text = _text()
    restore_section = text.split("cmd_env_restore()")[1].split("cmd_status()")[0]
    assert "compose_with" in restore_section and "down" in restore_section
    assert "restore_point.py restore" in restore_section
    assert "--journal /data/restore-journal.json" in restore_section
