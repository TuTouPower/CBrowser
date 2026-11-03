"""Stop command results survive retries and refuse operation-ID reuse."""

import pytest
from cbrowser.supervisor.operation_journal import OperationJournal


def test_completed_stop_is_replayable_after_restart(tmp_path):
    request = {"profile_id": "profile", "runtime_instance_id": "old_runtime"}
    result = {"profile_id": "profile", "status": "stopped"}
    journal = OperationJournal(tmp_path)
    assert journal.lookup("../operation", request) is None
    journal.complete("../operation", request, result)
    assert OperationJournal(tmp_path).lookup("../operation", request) == result
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_same_operation_id_cannot_target_another_runtime(tmp_path):
    journal = OperationJournal(tmp_path)
    journal.complete("operation", {"runtime_instance_id": "old"}, {"status": "stopped"})
    with pytest.raises(ValueError, match="different request"):
        journal.lookup("operation", {"runtime_instance_id": "new"})


def test_pending_command_identity_survives_coordinator_crash(tmp_path):
    OperationJournal(tmp_path).begin("operation", {"runtime_instance_id": "old"})
    recovered = OperationJournal(tmp_path)
    with pytest.raises(ValueError, match="different request"):
        recovered.begin("operation", {"runtime_instance_id": "new"})


def test_corrupt_journal_is_quarantined_and_treated_as_missing(tmp_path):
    request = {"runtime_instance_id": "old"}
    result = {"status": "stopped"}
    journal = OperationJournal(tmp_path)
    journal.complete("operation", request, result)
    record = next(tmp_path.glob("*.json"))
    record.write_text("{not-json", encoding="utf-8")

    restarted = OperationJournal(tmp_path)
    assert restarted.lookup("operation", request) is None
    assert not record.exists()
    quarantined = list(tmp_path.glob("*.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_text(encoding="utf-8") == "{not-json"

    restarted.complete("operation", request, result)
    assert OperationJournal(tmp_path).lookup("operation", request) == result
