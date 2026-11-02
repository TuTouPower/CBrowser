"""Builds and prepares the frontend static directory for Caddy in E2E tests."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .adapter_probe import inject_adapter_probe

logger = logging.getLogger("cbrowser.frontend_probe.host_builder")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FRONTEND_DIR = REPO_ROOT / "src" / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"


def ensure_frontend_build() -> Path:
    """Ensures Vite production build exists and is up to date."""
    if (
        not (DIST_DIR / "index.html").is_file()
        or not (DIST_DIR / "selkies").is_dir()
        or not (DIST_DIR / "selkies" / "selkies_adapter.js").is_file()
    ):
        logger.info("Building frontend in %s ...", FRONTEND_DIR)
        subprocess.run(
            ["npm", "run", "build", "--prefix", str(FRONTEND_DIR)],
            check=True,
            cwd=str(REPO_ROOT),
        )
    return DIST_DIR


def prepare_frontend_host(dest_dir: Path) -> Path:
    """Prepares dest_dir with Vite assets, Selkies client, and minimal host page."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dist = ensure_frontend_build()

    # 1. Copy assets and selkies from dist
    for name in ("assets", "selkies"):
        src = dist / name
        target = dest_dir / name
        if target.exists():
            shutil.rmtree(target)
        if src.is_dir():
            shutil.copytree(src, target)

    # Copy any other public static files (svg, ico)
    for item in dist.iterdir():
        if item.is_file() and item.name not in ("index.html", "session.js"):
            shutil.copy2(item, dest_dir / item.name)

    # 2. Bundle host entry with esbuild from src/frontend
    entry_tsx_path = "src/features/browser-session/host_entry.tsx"
    out_bundle_path = dest_dir / "session.js"
    cmd = [
        "npx",
        "esbuild",
        entry_tsx_path,
        "--bundle",
        "--format=esm",
        f"--outfile={out_bundle_path}",
    ]
    subprocess.run(cmd, check=True, cwd=str(FRONTEND_DIR))

    # 3. Find CSS file
    css_files = list((dest_dir / "assets").glob("*.css"))
    css_tag = (
        f'<link rel="stylesheet" href="/assets/{css_files[0].name}" />'
        if css_files
        else ""
    )

    # 4. Generate minimal host index.html mounting BrowserSessionView
    index_html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CBrowser Browser Session</title>
  {css_tag}
  <style>
    html, body, #root {{
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      overflow: hidden;
      background-color: #0a0a0a;
    }}
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/session.js"></script>
</body>
</html>
"""
    (dest_dir / "index.html").write_text(index_html_content, encoding="utf-8")
    inject_adapter_probe(dest_dir / "selkies" / "index.html")
    return dest_dir
