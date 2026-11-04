"""Unit contracts for the t029 automation compatibility probe harness."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "fixtures")
)

from automation_probe.harness import (  # noqa: E402
    MUST_MEDIATE_METHODS,
    CdpBridge,
    ObservationServer,
    ProbePrerequisiteMissing,
    XTestInput,
    build_report,
    classify_cdp_method,
    compare_level_samples,
    summarize_levels,
)


def _samples(value_by_field: dict[str, object], count: int = 5) -> list[dict]:
    return [dict(value_by_field) for _ in range(count)]


def test_compare_flags_only_reproducible_out_of_baseline_values() -> None:
    baseline = _samples({"focus": True, "ratio": 1})
    changed = _samples({"focus": False, "ratio": 1})
    changes = compare_level_samples(baseline, changed)
    assert [c["field"] for c in changes] == ["focus"]
    assert changes[0]["occurrences"] == 5

    noisy = _samples({"focus": True, "ratio": 1})
    noisy[0]["focus"] = False  # 1/5 is below the pre-registered threshold
    assert compare_level_samples(baseline, noisy) == []


def test_summarize_levels_requires_five_samples() -> None:
    baseline = _samples({"a": 1})
    summary = summarize_levels(
        {"L0": baseline, "L1": _samples({"a": 2}, count=3), "L2": _samples({"a": 1})}
    )
    assert summary["L0"]["verdict"] == "baseline"
    assert summary["L1"]["verdict"] == "insufficient"
    assert summary["L2"]["verdict"] == "no_change"


def test_classify_cdp_method_categories() -> None:
    assert classify_cdp_method("Browser.close") == "closes_shared_state"
    assert classify_cdp_method("Target.closeTarget") == "closes_shared_state"
    assert classify_cdp_method("Browser.setDownloadBehavior") == "download_policy"
    assert classify_cdp_method("Emulation.setEmulatedMedia") == "emulation_override"
    assert classify_cdp_method("Runtime.enable") == "domain_enable"
    assert classify_cdp_method("Input.dispatchMouseEvent") == "input_dispatch"
    assert classify_cdp_method("Runtime.evaluate") == "page_evaluation"
    # Attach-time state changers must not fall into "other": the spec's
    # state-changing list is defined by state_changing_methods(), which
    # only keeps classified categories.
    assert (
        classify_cdp_method("Page.addScriptToEvaluateOnNewDocument")
        == "script_injection"
    )
    assert classify_cdp_method("Target.setAutoAttach") == "target_attach"


def test_state_changing_methods_include_injection_and_attach() -> None:
    bridge = CdpBridge("ws://127.0.0.1:1/cdp")
    bridge.log = [
        {"direction": "client", "method": m, "category": classify_cdp_method(m)}
        for m in (
            "Page.addScriptToEvaluateOnNewDocument",
            "Target.setAutoAttach",
            "Browser.getVersion",
        )
    ]
    methods = {entry["method"] for entry in bridge.state_changing_methods()}
    assert methods == {
        "Page.addScriptToEvaluateOnNewDocument",
        "Target.setAutoAttach",
    }


def test_redact_report_value_keeps_signal_fields() -> None:
    report = build_report(
        sample={
            "cookieEnabled": True,
            "session_cookie": "abc",
            "authToken": "xyz",
            "nested": {"userAgent": "UA", "access_token": "t"},
        }
    )
    sample = report["sample"]
    assert sample["cookieEnabled"] is True
    assert sample["session_cookie"] == "<redacted>"
    assert sample["authToken"] == "<redacted>"
    assert sample["nested"]["userAgent"] == "UA"
    assert sample["nested"]["access_token"] == "<redacted>"


def test_redact_report_value_catches_api_key_spellings() -> None:
    report = build_report(
        sample={"api_key": "k1", "apiKey": "k2", "apikey": "k3", "monkey": "v"}
    )
    sample = report["sample"]
    assert sample["api_key"] == "<redacted>"
    assert sample["apiKey"] == "<redacted>"
    assert sample["apikey"] == "<redacted>"
    assert sample["monkey"] == "v"
    assert classify_cdp_method("Page.navigate") == "navigation"
    assert classify_cdp_method("Browser.getVersion") == "other"
    for method in (
        "Browser.close",
        "Browser.setDownloadBehavior",
        "Emulation.setDeviceMetricsOverride",
        "Page.addScriptToEvaluateOnNewDocument",
    ):
        assert method in MUST_MEDIATE_METHODS


def test_redact_report_value_catches_private_key_and_plural_forms() -> None:
    report = build_report(
        sample={
            "private_key": "k1",
            "cookies": "k2",
            "api_keys": "k3",
            "tokens": "k4",
            "secrets": "k5",
            "passwords": "k6",
            "credentials": "k7",
            "key": "event-field",
            "monkey": "v",
            "cookieEnabled": True,
        }
    )
    sample = report["sample"]
    for name in (
        "private_key",
        "cookies",
        "api_keys",
        "tokens",
        "secrets",
        "passwords",
        "credentials",
    ):
        assert sample[name] == "<redacted>"
    assert sample["key"] == "event-field"
    assert sample["monkey"] == "v"
    assert sample["cookieEnabled"] is True


def test_build_report_redacts_credentials_and_home_paths() -> None:
    report = build_report(
        note=f"token cbat_abcdef123456 at {Path.home()}/secret place",
        nested={"authorization": "Bearer cbat_abcdef123456", "ok": 1},
    )
    assert report["schema"] == "automation-probe-report/v1"
    assert "cbat_abcdef" not in str(report)
    assert str(Path.home()) not in str(report)
    assert report["nested"]["authorization"] == "<redacted>"
    assert report["toolchain"]["playwright"] == "1.64.1"
    assert report["toolchain"]["ego_lite_reference_commit"] == (
        "12407167f84a58af24044f072868051952131491"
    )


def test_xtest_input_emits_expected_commands() -> None:
    sent: dict[str, Any] = {}

    class _Result:
        returncode = 0
        stderr = ""

    def fake_runner(cmd, **kwargs):  # noqa: ANN001, ANN202
        sent["cmd"] = cmd
        sent.update(kwargs)
        return _Result()

    driver = XTestInput(":99", xte_path="/usr/bin/xte", runner=fake_runner)
    driver.click(120, 45)
    assert sent["cmd"] == ["/usr/bin/xte"]
    assert sent["input"] == "mousemove 120 45\nmousedown 1\nmouseup 1\n"
    assert sent["env"]["DISPLAY"] == ":99"

    driver.scroll(10, 10, -2)
    assert sent["input"] == "mousemove 10 10\nmouseclick 5\nmouseclick 5\n"

    with pytest.raises(ProbePrerequisiteMissing):
        XTestInput(":99", xte_path="", runner=fake_runner)


def test_observation_server_serves_pages_and_download() -> None:
    import urllib.request

    with ObservationServer() as server:
        main = urllib.request.urlopen(server.url + "/").read().decode()
        frame = urllib.request.urlopen(server.url + "/frame").read().decode()
        with urllib.request.urlopen(server.url + "/download") as response:
            body = response.read()
            disposition = response.headers["Content-Disposition"]
    assert 'id="pad"' in main and 'id="bu-toggle"' in main
    assert 'id="frame-pad"' in frame
    assert body == b"cbrowser-probe-download\n"
    assert "probe-download.txt" in disposition
