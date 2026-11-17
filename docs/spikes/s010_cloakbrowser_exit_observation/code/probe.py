#!/usr/bin/env python3
"""
probe_v2.py: Hardened fail-closed verification suite for CloakBrowser 0.6.4 SDK
process lifecycle observation, FD 3/4 remote-debugging-pipe penetration,
exact exit code capture (normal 0 vs SIGKILL 137/-9), and SDK owner-loss characterization.

History preserved: probe.py and original logs remain intact.
"""

import os
import sys
import time
import json
import signal
import threading
import subprocess
import cloakbrowser

REAL_CHROME = os.environ.get(
    "REAL_CHROME_BINARY", "/opt/cloakbrowser/chromium-146.0.7680.177.3/chrome"
)
STATUS_FILE = "/tmp/cbrowser_v2_status.json"
OWNER_META_FILE = "/tmp/cbrowser_v2_owner_meta.json"
WRAPPER_PATH = "/tmp/cbrowser_v2_wrapper.py"
FAIL_WRAPPER_PATH = "/tmp/cbrowser_v2_fail_wrapper.py"


def write_wrapper(path: str, pass_fds_enabled: bool, record_stderr: bool = False):
    """
    Generate controlled launcher wrapper.
    When pass_fds_enabled=True: pass_fds=(3, 4), default close_fds=True (no RuntimeWarning).
    When pass_fds_enabled=False: close_fds=True, pass_fds=None (closing FD 3/4).
    """
    pass_clause = (
        """pass_fds = [fd for fd in (3, 4) if os.path.exists(f"/proc/self/fd/{fd}")]
p = subprocess.Popen([REAL_CHROME] + sys.argv[1:], pass_fds=pass_fds)
"""
        if pass_fds_enabled
        else """# Deliberately do not pass FD 3/4
p = subprocess.Popen([REAL_CHROME] + sys.argv[1:], close_fds=True, stderr=subprocess.PIPE)
"""
    )

    stderr_handling = (
        """out, err = p.communicate()
ret = p.returncode
with open("/tmp/cbrowser_fail_stderr.log", "wb") as ef:
    ef.write(err or b"")
"""
        if record_stderr
        else """ret = p.wait()
"""
    )

    code = f"""#!/usr/bin/env python3
import sys, subprocess, os, json, time, signal

REAL_CHROME = "{REAL_CHROME}"
STATUS_FILE = "{STATUS_FILE}"

{pass_clause}

starttime = None
try:
    with open(f"/proc/{{p.pid}}/stat") as f:
        stat_parts = f.read().split()
        starttime = stat_parts[21]
except Exception as e:
    starttime = f"err:{{e}}"

meta = {{
    "wrapper_pid": os.getpid(),
    "chrome_pid": p.pid,
    "chrome_starttime": starttime,
    "launch_time": time.time(),
    "status": "running",
    "exit_code": None,
    "term_signal": None,
    "exit_time": None,
    "raw_wait_code": None,
    "is_signal_termination": False
}}

with open(STATUS_FILE + ".tmp", "w") as f:
    json.dump(meta, f, indent=2)
os.replace(STATUS_FILE + ".tmp", STATUS_FILE)

def forward_signal(signum, frame):
    try:
        p.send_signal(signum)
    except Exception:
        pass

for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    try:
        signal.signal(sig, forward_signal)
    except Exception:
        pass

{stderr_handling}

meta["status"] = "exited"
meta["exit_time"] = time.time()
meta["raw_wait_code"] = ret

if ret < 0:
    meta["exit_code"] = 128 + (-ret)
    meta["term_signal"] = -ret
    meta["is_signal_termination"] = True
else:
    meta["exit_code"] = ret
    meta["term_signal"] = None
    meta["is_signal_termination"] = False

with open(STATUS_FILE + ".tmp", "w") as f:
    json.dump(meta, f, indent=2)
os.replace(STATUS_FILE + ".tmp", STATUS_FILE)

sys.exit(meta["exit_code"])
"""
    with open(path, "w") as f:
        f.write(code)
    os.chmod(path, 0o755)


def get_proc_status(pid: int) -> dict:
    info = {"exists": False, "state": None, "exe": None, "starttime": None}
    if not os.path.exists(f"/proc/{pid}"):
        return info
    info["exists"] = True
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("State:"):
                    info["state"] = line.split()[1]
                    break
    except Exception:
        pass
    try:
        info["exe"] = os.readlink(f"/proc/{pid}/exe")
    except Exception:
        pass
    try:
        with open(f"/proc/{pid}/stat") as f:
            info["starttime"] = f.read().split()[21]
    except Exception:
        pass
    return info


def run_all_checks():
    print("=" * 70)
    print("PROBE V2: CloakBrowser 0.6.4 SDK Process Lifecycle & Exit Hardened Suite")
    print(f"SDK Version: {cloakbrowser.__version__}")
    print(f"Target Binary: {REAL_CHROME}")
    print("=" * 70)

    results = {}

    # -------------------------------------------------------------
    # Check 1: Strict TypeError validation for kwargs executable_path
    # -------------------------------------------------------------
    print("\n[Check 1] Fail-closed: executable_path kwargs duplicate error...")
    try:
        cloakbrowser.launch_persistent_context(
            "/tmp/p_v2_chk1", headless=True, executable_path=REAL_CHROME, timeout=5000
        )
        results["check_1_kwargs_collision"] = "UNEXPECTED_PASS"
        print("  FAIL: executable_path was accepted without exception!")
    except TypeError as te:
        err_msg = str(te)
        expected_substr = "got multiple values for keyword argument 'executable_path'"
        if expected_substr in err_msg:
            results["check_1_kwargs_collision"] = "PASS"
            print(f"  PASS: TypeError confirmed with exact message: {err_msg}")
        else:
            results["check_1_kwargs_collision"] = f"FAIL_WRONG_TYPE_ERROR: {err_msg}"
            print(
                f"  FAIL: TypeError occurred but message did not match expected: {err_msg}"
            )
    except Exception as e:
        results["check_1_kwargs_collision"] = f"FAIL_OTHER_EXC: {type(e).__name__}"
        print(f"  FAIL: Expected TypeError but got {type(e).__name__}: {e}")

    # -------------------------------------------------------------
    # Check 2: Fail-closed: FD 3/4 closure verified with exact stderr
    # -------------------------------------------------------------
    print(
        "\n[Check 2] Fail-closed: Negative check with close_fds=True (FD 3/4 closed)..."
    )
    if os.path.exists("/tmp/cbrowser_fail_stderr.log"):
        os.remove("/tmp/cbrowser_fail_stderr.log")
    write_wrapper(FAIL_WRAPPER_PATH, pass_fds_enabled=False, record_stderr=True)
    os.environ["CLOAKBROWSER_BINARY_PATH"] = FAIL_WRAPPER_PATH
    t0 = time.time()
    try:
        ctx = cloakbrowser.launch_persistent_context(
            "/tmp/p_v2_chk2", headless=True, timeout=8000
        )
        results["check_2_negative_fd"] = "UNEXPECTED_PASS"
        print("  FAIL: Browser launched when FDs were closed!")
        ctx.close()
    except Exception as e:
        dur = time.time() - t0
        exc_type = type(e).__name__
        stderr_evidence = ""
        if os.path.exists("/tmp/cbrowser_fail_stderr.log"):
            with open("/tmp/cbrowser_fail_stderr.log", "r", errors="replace") as sf:
                stderr_evidence = sf.read()

        expected_stderr_phrase = "Remote debugging pipe file descriptors are not open"
        has_stderr_evidence = expected_stderr_phrase in stderr_evidence
        is_target_closed = exc_type == "TargetClosedError"

        print(f"  Caught {exc_type} in {dur:.2f}s.")
        print(
            f"  Chrome stderr evidence found: {has_stderr_evidence} (output: {stderr_evidence.strip()[:100]})"
        )

        if is_target_closed and has_stderr_evidence:
            results["check_2_negative_fd"] = "PASS"
            print(
                "  PASS: Confirmed TargetClosedError caused precisely by missing FD 3/4."
            )
        else:
            results["check_2_negative_fd"] = (
                f"FAIL_EVIDENCE_MISMATCH: exc={exc_type}, has_evidence={has_stderr_evidence}"
            )
            print(f"  FAIL: Incomplete evidence for FD closure failure.")

    # Prepare standard positive wrapper (pass_fds=(3, 4), close_fds=True default)
    write_wrapper(WRAPPER_PATH, pass_fds_enabled=True, record_stderr=False)
    os.environ["CLOAKBROWSER_BINARY_PATH"] = WRAPPER_PATH

    # -------------------------------------------------------------
    # Check 3: Positive Check - Clean BrowserContext.close() -> exit 0
    # -------------------------------------------------------------
    print("\n[Check 3] Positive check: Clean BrowserContext.close()...")
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)
    try:
        ctx3 = cloakbrowser.launch_persistent_context(
            "/tmp/p_v2_chk3", headless=True, timeout=15000
        )
        with open(STATUS_FILE) as f:
            rec3_running = json.load(f)
        chrome_pid3 = rec3_running["chrome_pid"]
        starttime3 = rec3_running["chrome_starttime"]

        # Verify /proc metadata
        proc_stat3 = get_proc_status(chrome_pid3)
        assert proc_stat3["exists"], f"/proc/{chrome_pid3} does not exist"
        assert proc_stat3["exe"] == REAL_CHROME, (
            f"Expected exe {REAL_CHROME}, got {proc_stat3['exe']}"
        )
        assert proc_stat3["starttime"] == starttime3, "Starttime mismatch"
        print(
            f"  Verified running Chrome: PID={chrome_pid3}, exe={proc_stat3['exe']}, starttime={starttime3}"
        )

        ctx3.close()
        time.sleep(0.4)

        with open(STATUS_FILE) as f:
            rec3_final = json.load(f)

        assert rec3_final["chrome_pid"] == chrome_pid3, (
            "Chrome PID changed in final record"
        )
        assert rec3_final["chrome_starttime"] == starttime3, (
            "Chrome starttime changed in final record"
        )
        assert rec3_final["raw_wait_code"] == 0, (
            f"Expected raw_wait_code 0, got {rec3_final['raw_wait_code']}"
        )
        assert rec3_final["exit_code"] == 0, (
            f"Expected exit_code 0, got {rec3_final['exit_code']}"
        )
        assert rec3_final["term_signal"] is None, (
            f"Expected None signal, got {rec3_final['term_signal']}"
        )
        assert rec3_final["is_signal_termination"] is False

        results["check_3_normal_close"] = "PASS"
        print(
            "  PASS: Normal exit code 0 verified with matched PID/starttime and verified /proc/exe."
        )
    except Exception as e:
        results["check_3_normal_close"] = f"FAIL: {type(e).__name__}: {e}"
        print(f"  FAIL: {e}")

    # -------------------------------------------------------------
    # Check 4: Abnormal Check - Direct SIGKILL on Chrome PID
    # -------------------------------------------------------------
    print("\n[Check 4] Abnormal check: Direct SIGKILL on real Chrome PID...")
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)
    try:
        ctx4 = cloakbrowser.launch_persistent_context(
            "/tmp/p_v2_chk4", headless=True, timeout=15000
        )
        with open(STATUS_FILE) as f:
            rec4_running = json.load(f)
        chrome_pid4 = rec4_running["chrome_pid"]
        starttime4 = rec4_running["chrome_starttime"]

        proc_stat4 = get_proc_status(chrome_pid4)
        assert proc_stat4["exists"], f"/proc/{chrome_pid4} does not exist"
        assert proc_stat4["exe"] == REAL_CHROME, (
            f"Expected exe {REAL_CHROME}, got {proc_stat4['exe']}"
        )
        assert proc_stat4["starttime"] == starttime4, "Starttime mismatch"
        print(
            f"  Verified running Chrome: PID={chrome_pid4}, exe={proc_stat4['exe']}, starttime={starttime4}"
        )

        page4 = ctx4.pages[0] if ctx4.pages else ctx4.new_page()
        page4.goto("data:text/html,<h1>Alive</h1>")

        def killer():
            time.sleep(0.8)
            print(f"  [Action] Sending SIGKILL to real Chrome PID {chrome_pid4}...")
            os.kill(chrome_pid4, signal.SIGKILL)

        kt = threading.Thread(target=killer)
        kt.start()

        driver_err = None
        try:
            for _ in range(25):
                time.sleep(0.15)
                page4.evaluate("1 + 1")
        except Exception as exc:
            driver_err = exc
            print(f"  Driver Observation: Caught {type(exc).__name__}")

        kt.join()
        time.sleep(0.4)

        with open(STATUS_FILE) as f:
            rec4_final = json.load(f)

        assert rec4_final["chrome_pid"] == chrome_pid4, (
            "Chrome PID changed in final record"
        )
        assert rec4_final["chrome_starttime"] == starttime4, (
            "Chrome starttime changed in final record"
        )
        assert rec4_final["raw_wait_code"] == -9, (
            f"Expected raw_wait_code -9, got {rec4_final['raw_wait_code']}"
        )
        assert rec4_final["exit_code"] == 137, (
            f"Expected exit_code 137, got {rec4_final['exit_code']}"
        )
        assert rec4_final["term_signal"] == 9, (
            f"Expected signal 9, got {rec4_final['term_signal']}"
        )
        assert rec4_final["is_signal_termination"] is True

        results["check_4_sigkill_capture"] = "PASS"
        print("  PASS: Direct SIGKILL captured: raw=-9, exit_code=137, term_signal=9.")
    except Exception as e:
        results["check_4_sigkill_capture"] = f"FAIL: {type(e).__name__}: {e}"
        print(f"  FAIL: {e}")

    # -------------------------------------------------------------
    # Check 5: Characterization: SDK Owner Process Loss Observation
    # -------------------------------------------------------------
    print("\n[Check 5] Characterization: SDK Owner Process SIGKILL Observation...")
    if os.path.exists(STATUS_FILE):
        os.remove(STATUS_FILE)
    if os.path.exists(OWNER_META_FILE):
        os.remove(OWNER_META_FILE)

    owner_script_path = "/tmp/cbrowser_v2_owner_subproc.py"
    owner_code = f"""#!/usr/bin/env python3
import os, sys, time, json
import cloakbrowser

os.environ["CLOAKBROWSER_BINARY_PATH"] = "{WRAPPER_PATH}"
ctx = cloakbrowser.launch_persistent_context("/tmp/p_v2_owner", headless=True)

rec = None
for _ in range(50):
    if os.path.exists("{STATUS_FILE}"):
        with open("{STATUS_FILE}") as f:
            rec = json.load(f)
            if rec.get("chrome_pid"):
                break
    time.sleep(0.1)

meta = {{
    "owner_pid": os.getpid(),
    "wrapper_pid": rec.get("wrapper_pid"),
    "chrome_pid": rec.get("chrome_pid"),
    "chrome_starttime": rec.get("chrome_starttime"),
    "ready": True
}}
with open("{OWNER_META_FILE}", "w") as f:
    json.dump(meta, f)

while True:
    time.sleep(1)
"""
    with open(owner_script_path, "w") as f:
        f.write(owner_code)
    os.chmod(owner_script_path, 0o755)

    recorded_pids = []
    owner_proc = None
    try:
        owner_proc = subprocess.Popen(["python3", owner_script_path])
        recorded_pids.append(owner_proc.pid)

        owner_meta = None
        for _ in range(100):
            if os.path.exists(OWNER_META_FILE):
                try:
                    with open(OWNER_META_FILE) as f:
                        owner_meta = json.load(f)
                        if owner_meta.get("ready"):
                            break
                except Exception:
                    pass
            time.sleep(0.1)

        assert owner_meta is not None, "Owner process did not write metadata in time"
        owner_pid = owner_meta["owner_pid"]
        chrome_pid5 = owner_meta["chrome_pid"]
        wrapper_pid5 = owner_meta["wrapper_pid"]
        starttime5 = owner_meta["chrome_starttime"]

        recorded_pids.extend([chrome_pid5, wrapper_pid5])

        # Verify running before kill
        chrome_stat_before = get_proc_status(chrome_pid5)
        assert chrome_stat_before["exists"], f"Chrome PID {chrome_pid5} not running"
        assert chrome_stat_before["exe"] == REAL_CHROME, (
            f"Chrome exe mismatch: {chrome_stat_before['exe']}"
        )
        print(
            f"  Owner ready: owner_pid={owner_pid}, chrome_pid={chrome_pid5}, starttime={starttime5}"
        )

        # Kill ONLY owner process
        print(f"  [Action] Sending SIGKILL to owner PID {owner_pid}...")
        os.kill(owner_pid, signal.SIGKILL)

        # 5-second observation timeline before any cleanup
        timeline = []
        for step in range(10):
            time.sleep(0.5)
            elapsed = round((step + 1) * 0.5, 1)
            o_st = get_proc_status(owner_pid)
            c_st = get_proc_status(chrome_pid5)
            w_st = get_proc_status(wrapper_pid5)

            rec_now = {}
            if os.path.exists(STATUS_FILE):
                try:
                    with open(STATUS_FILE) as f:
                        rec_now = json.load(f)
                except Exception:
                    pass

            snap = {
                "t_sec": elapsed,
                "owner_state": o_st["state"] if o_st["exists"] else "gone",
                "chrome_state": c_st["state"] if c_st["exists"] else "gone",
                "wrapper_state": w_st["state"] if w_st["exists"] else "gone",
                "wrapper_reported_status": rec_now.get("status"),
                "raw_wait_code": rec_now.get("raw_wait_code"),
                "exit_code": rec_now.get("exit_code"),
                "term_signal": rec_now.get("term_signal"),
            }
            timeline.append(snap)

        with open("/tmp/cbrowser_v2_owner_loss_timeline.json", "w") as f:
            json.dump(timeline, f, indent=2)

        # Read final recorded status before cleanup
        final_rec5 = {}
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE) as f:
                final_rec5 = json.load(f)

        print("\n  --- Timeline Observation Before Any Cleanup ---")
        for pt in timeline:
            print(
                f"    t={pt['t_sec']}s: owner={pt['owner_state']}, chrome={pt['chrome_state']}, wrapper_status={pt['wrapper_reported_status']}, raw_wait={pt['raw_wait_code']}, exit={pt['exit_code']}"
            )

        print(
            f"\n  Final record before cleanup: exit_code={final_rec5.get('exit_code')}, raw_wait_code={final_rec5.get('raw_wait_code')}, signal={final_rec5.get('term_signal')}"
        )

        # Characterization assertion:
        # We verify that the observation is valid and consistent:
        # Chrome is indeed terminated after pipe loss, AND wrapper captured the wait result.
        assert timeline[-1]["chrome_state"] == "gone", (
            "Chrome unexpectedly remained alive after owner loss"
        )
        assert final_rec5.get("status") == "exited", (
            "Wrapper did not record exited status"
        )
        results["check_5_owner_loss_characterization"] = "PASS"
        print(
            f"  PASS: Characterization completed. Owner death triggered Chrome exit code {final_rec5.get('exit_code')} via debug-pipe EOF."
        )
    except Exception as e:
        results["check_5_owner_loss_characterization"] = (
            f"FAIL: {type(e).__name__}: {e}"
        )
        print(f"  FAIL in check 5: {e}")
    finally:
        # Cleanup only recorded pids
        print("  [Cleanup] Cleaning up recorded PIDs in finally block...")
        for p in recorded_pids:
            if p and os.path.exists(f"/proc/{p}"):
                try:
                    os.kill(p, signal.SIGKILL)
                except Exception:
                    pass
        if owner_proc:
            try:
                owner_proc.wait(timeout=1)
            except Exception:
                pass

    # -------------------------------------------------------------
    # Summary Validation: Exactly 5 expected keys, all PASS
    # -------------------------------------------------------------
    expected_keys = [
        "check_1_kwargs_collision",
        "check_2_negative_fd",
        "check_3_normal_close",
        "check_4_sigkill_capture",
        "check_5_owner_loss_characterization",
    ]

    print("\n" + "=" * 70)
    print("PROBE V2 FINAL SUMMARY:")
    all_matched = list(results.keys()) == expected_keys
    all_pass = all(results.get(k) == "PASS" for k in expected_keys)

    for k in expected_keys:
        print(f"  {k}: {results.get(k, 'MISSING')}")
    print(f"Exact keys matched: {all_matched}")
    print(f"All checks PASS: {all_pass}")
    print("=" * 70)

    return all_matched and all_pass


if __name__ == "__main__":
    success = run_all_checks()
    sys.exit(0 if success else 1)
