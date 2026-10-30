import sys
import time


def run_burner(duration_sec: float, target_load: float = 1.0) -> None:
    """Burn CPU with controlled duty cycle."""
    end_time = time.time() + duration_sec
    chunk = 0.1
    busy_time = chunk * max(0.0, min(1.0, target_load))
    sleep_time = chunk - busy_time

    while time.time() < end_time:
        t_start = time.time()
        # Busy loop
        while time.time() - t_start < busy_time:
            _ = [x * x for x in range(5000)]
        if sleep_time > 0.001:
            time.sleep(sleep_time)


if __name__ == "__main__":
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    load = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    run_burner(dur, load)
