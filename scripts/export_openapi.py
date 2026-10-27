"""Export OpenAPI schema directly from the FastAPI application."""

from __future__ import annotations

import json
from pathlib import Path

from cbrowser.api.app import create_app


def export_openapi_schema(output_path: Path | str | None = None) -> Path:
    app = create_app()
    openapi_schema = app.openapi()

    if output_path is None:
        root_dir = Path(__file__).resolve().parent.parent
        dest = root_dir / "schemas" / "openapi" / "cbrowser_v1.json"
    else:
        dest = Path(output_path).resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(openapi_schema, indent=2), encoding="utf-8")
    return dest


if __name__ == "__main__":
    out = export_openapi_schema()
    print(f"OpenAPI schema exported to {out}")
