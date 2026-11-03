"""Per-profile CJK font bundles via a generated fontconfig file.

The Browser image ships the WenQuanYi bundles outside fontconfig's default
scan paths (``/opt/cbrowser-fonts/<bundle>``), so a profile only sees a CJK
font when the runner generates a profile fontconfig file that includes the
system configuration and appends exactly that bundle's directory, then
points Chrome at it through ``FONTCONFIG_FILE``. ``none`` generates no file
and clears the variable, which keeps the default no-CJK fingerprint.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("cbrowser.runtime_agent.fontconfig")

FONT_BUNDLE_ROOT = Path("/opt/cbrowser-fonts")
FONT_BUNDLE_DIRS: dict[str, Path] = {
    "wqy-microhei": FONT_BUNDLE_ROOT / "wqy-microhei",
    "wqy-zenhei": FONT_BUNDLE_ROOT / "wqy-zenhei",
}
SYSTEM_FONTCONFIG = "/etc/fonts/fonts.conf"
PROFILE_FONTCONFIG_FILENAME = "profile-fonts.conf"


def build_fontconfig_xml(
    font_bundle: str, *, bundle_root: Path = FONT_BUNDLE_ROOT
) -> str:
    """Render the profile fontconfig file for one non-``none`` bundle."""
    if font_bundle not in FONT_BUNDLE_DIRS:
        raise ValueError(f"Unknown font bundle: {font_bundle!r}")
    bundle_dir = bundle_root / font_bundle
    return (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <include>{SYSTEM_FONTCONFIG}</include>\n"
        f"  <dir>{bundle_dir}</dir>\n"
        "</fontconfig>\n"
    )


def prepare_profile_fontconfig(
    run_dir: Path,
    font_bundle: str,
    *,
    bundle_root: Path = FONT_BUNDLE_ROOT,
) -> Path | None:
    """Write the profile fontconfig file into ``run_dir``.

    Returns ``None`` for the ``none`` bundle (any stale generated file is
    removed so an old bundle cannot linger) and when generation fails: the
    fallback keeps the default system configuration, whose scan paths
    contain no CJK bundle, instead of risking a broken font setup for the
    whole browser. The file lands via tmp + ``os.replace`` + fsync, the
    same atomic-write discipline as the runtime event storage.
    """
    target = run_dir / PROFILE_FONTCONFIG_FILENAME
    if font_bundle == "none":
        target.unlink(missing_ok=True)
        return None
    try:
        xml = build_fontconfig_xml(font_bundle, bundle_root=bundle_root)
        run_dir.mkdir(parents=True, exist_ok=True)
        tmp = run_dir / (PROFILE_FONTCONFIG_FILENAME + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(xml)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(0o600)
        os.replace(tmp, target)
        dir_fd = os.open(run_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except (OSError, ValueError):
        logger.error(
            "Failed to write profile fontconfig for bundle %s; "
            "falling back to the system font configuration",
            font_bundle,
        )
        return None
    return target
