"""One initial failure followed by three automatic recovery attempts."""

from enum import StrEnum

AUTO_RETRY_DELAYS = (2.0, 10.0, 30.0)
BLOCK_AFTER_RUNTIME_FAILURES = 1 + len(AUTO_RETRY_DELAYS)


class ExitReason(StrEnum):
    NORMAL = "normal"
    ABNORMAL = "abnormal"
    ABNORMAL_LOST = "abnormal_lost"
    PROCESS_OBSERVATION_LOST = "process_observation_lost"
    STARTUP_FAILURE = "startup_failure"
    CONTAINER_TERMINATED = "container_terminated"
    MISSING_RUNTIME = "missing_runtime"
    CONTAINER_EXIT = "container_exit"
    AGENT_EXIT = "agent_exit"
    NORMAL_EXIT = "normal_exit"
    CRASH = "crash"
    SIGTERM = "sigterm"
    SIGKILL = "sigkill"
    OOM = "oom"
    UNKNOWN = "unknown"
    ERROR = "error"
    BROWSER_SEGFAULT = "browser_segfault"
