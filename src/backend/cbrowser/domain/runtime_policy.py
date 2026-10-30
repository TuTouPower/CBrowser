"""One initial failure followed by three automatic recovery attempts."""

AUTO_RETRY_DELAYS = (2.0, 10.0, 30.0)
BLOCK_AFTER_RUNTIME_FAILURES = 1 + len(AUTO_RETRY_DELAYS)
