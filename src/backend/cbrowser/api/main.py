"""Production entrypoint for CBrowser Control API."""

from __future__ import annotations

import os
from pathlib import Path

from cbrowser.api.app import create_app
from cbrowser.network_config import DEFAULT_HTTPS_PORT

db_path = os.environ.get("CBROWSER_DB_PATH", "/data/db/cbrowser.db")
app = create_app(db_path=Path(db_path))

if __name__ == "__main__":
    import uvicorn

    # The standalone entrypoint defaults to the single deployment port
    # constant (t054): no second literal copy of the default port.
    port = int(os.environ.get("CBROWSER_PORT", str(DEFAULT_HTTPS_PORT)))
    host = os.environ.get("CBROWSER_HOST", "127.0.0.1")
    uvicorn.run("cbrowser.api.main:app", host=host, port=port, log_level="info")
