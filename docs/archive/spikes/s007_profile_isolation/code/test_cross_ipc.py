import sys
from pixelflux import ScreenCapture, CaptureSettings

def main():
    cap = ScreenCapture()
    s = CaptureSettings()
    try:
        cap.start_capture(lambda b: None, s)
        print("FAIL: Pixelflux capture unexpectedly succeeded across IPC boundary!")
        sys.exit(1)
    except Exception as e:
        err = str(e)
        print("CAUGHT_EXPECTED:", err)
        if "error_kind: Access" in err or "error_code: 10" in err:
            print("PASS: Pixelflux rejected with Access error_code 10.")
            sys.exit(0)
        else:
            print(f"FAIL: Unexpected error: {err}")
            sys.exit(2)

if __name__ == "__main__":
    main()
