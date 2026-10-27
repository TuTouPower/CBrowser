"""Production entrypoint for CBrowser Control API v2."""

from __future__ import annotations

import os
from pathlib import Path

from cbrowser.api.app import create_app

db_path = os.environ.get("CBROWSER_DB_PATH", "/data/cbrowser.db")
app = create_app(db_path=Path(db_path))

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("CBROWSER_PORT", "56661"))
    host = os.environ.get("CBROWSER_HOST", "127.0.0.1")
    uvicorn.run("cbrowser.api.main:app", host=host, port=port, log_level="info")
