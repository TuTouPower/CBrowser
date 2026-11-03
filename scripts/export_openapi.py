"""Export OpenAPI schema directly from the FastAPI application."""

from __future__ import annotations

import json
from pathlib import Path

from cbrowser.api.app import create_app


def export_openapi_schema(
    output_path: Path | str | None = None, *, internal: bool = False
) -> Path:
    app = create_app(include_internal_schema=internal)
    openapi_schema = app.openapi()

    if output_path is None:
        root_dir = Path(__file__).resolve().parent.parent
        name = "cbrowser_internal.json" if internal else "cbrowser_v1.json"
        dest = root_dir / "schemas" / "openapi" / name
    else:
        dest = Path(output_path).resolve()

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(openapi_schema, indent=2) + "\n", encoding="utf-8")
    return dest


if __name__ == "__main__":
    out = export_openapi_schema()
    internal_out = export_openapi_schema(internal=True)
    print(f"OpenAPI schema exported to {out}")
    print(f"Internal OpenAPI schema exported to {internal_out}")
