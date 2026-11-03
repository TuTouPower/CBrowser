"""Frontend source-freshness gate."""

from pathlib import Path

import pytest
from scripts.verify_frontend_dist import (
    verify_frontend_build_freshness,
    write_frontend_build_stamp,
)


def test_stamp_rejects_stale_source(tmp_path: Path):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    (frontend / "src" / "main.ts").write_text("one", encoding="utf-8")
    (frontend / "index.html").write_text("<html></html>", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    write_frontend_build_stamp(dist, frontend)
    verify_frontend_build_freshness(dist, frontend)
    (frontend / "src" / "main.ts").write_text("two", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        verify_frontend_build_freshness(dist, frontend)
