"""Write the frontend source fingerprint into the production dist."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.verify_frontend_dist import REPO_ROOT, write_frontend_build_stamp

if __name__ == "__main__":
    write_frontend_build_stamp(REPO_ROOT / "src" / "frontend" / "dist")
    print("Wrote frontend build stamp")
