import json
import logging
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO)
subprocess.run([sys.executable, str(root / "extra_harness.py")], check=True)
result = json.loads((root / "extra_harness_result.json").read_text())
assert result["cjk_punctuation"]["match"] is True, "CJK punctuation mismatch"
assert result["cancellation"]["preedit_streamed"] is True, "Preedit not delivered"
assert result["cancellation"]["post_cancel_empty"] is True, "Cancellation did not clear"
assert result["emoji"]["match"] is True, "Emoji mismatch"
assert result["clipboard_unmodified"] is True, "Clipboard modified"
logging.info("All extra native composition observations verified")
