"""Per-profile fontconfig generation with an explicit directory whitelist.

The Browser image keeps its base open-source fonts under
``/opt/cbrowser-base-fonts`` so that CloakBrowser's documented minimum
font packages are installed. Those fonts are Linux-flavoured (WenQuanYi,
Unifont, FreeFont, IPAGothic, Loma) and must NOT be visible to a fingerprint
Profile: plan 6.8 requires Linux-only fonts to be invisible on both windows
and macos platforms. The Supervisor mounts a bound platform font set
read-only under ``/run/cbrowser/fonts/{platform}/{set_id}``. A bound set
owns the whole ``FONTCONFIG_FILE`` whitelist; when no set is bound the
Profile falls back to the base font directory so Chrome can render, and the
runtime status marks that Linux base fonts are exposed. The system
configuration is never included.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from xml.sax.saxutils import escape

logger = logging.getLogger("cbrowser.runtime_agent.fontconfig")

BASE_FONTS_DIR = Path("/opt/cbrowser-base-fonts")
FONT_SET_MOUNT_ROOT = Path("/run/cbrowser/fonts")
PROFILE_FONTCONFIG_FILENAME = "profile-fonts.conf"
PLATFORM_FONTS_UNCONFIGURED = (
    "platform_fonts_unconfigured: linux base fonts exposed"
)


def profile_font_dirs(platform: str, font_set_id: str | None) -> list[Path]:
    """Select the FONTCONFIG_FILE whitelist for a Profile.

    A bound platform font set is the only visible directory. With no set
    bound (AC-006, "platform fonts not configured"), fall back to the base
    open-source fonts so Chrome can still render pages; the runtime status
    marks that Linux base fonts are exposed in that state.
    """
    if font_set_id:
        return [FONT_SET_MOUNT_ROOT / platform / font_set_id]
    return [BASE_FONTS_DIR]


def build_fontconfig_xml(dirs: list[Path | str]) -> str:
    """Render a fontconfig file that scans only ``dirs``.

    The system configuration is deliberately not included: doing so would
    re-expose every font under the default scan paths. An empty ``dirs`` is
    valid and yields a config with no ``<dir>`` entries; callers decide which
    directories to whitelist via :func:`profile_font_dirs`.
    """
    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">',
        "<fontconfig>",
        "  <cachedir>/tmp/cbrowser-fontconfig-cache</cachedir>",
    ]
    for directory in dirs:
        lines.append(f"  <dir>{escape(str(directory))}</dir>")
    lines.append("</fontconfig>")
    return "\n".join(lines) + "\n"


def prepare_profile_fontconfig(
    run_dir: Path,
    dirs: list[Path | str],
) -> Path | None:
    """Write the profile fontconfig file into ``run_dir``.

    Any ``dirs`` value produces a file. Callers pass the bound platform set
    or (when unbound) the base font directory. Returns ``None`` only when
    generation fails, keeping the best-effort fallback that never blocks
    browser startup. The file lands via tmp + ``os.replace`` + fsync.
    """
    target = run_dir / PROFILE_FONTCONFIG_FILENAME
    tmp = run_dir / (PROFILE_FONTCONFIG_FILENAME + ".tmp")
    try:
        xml = build_fontconfig_xml(dirs)
        run_dir.mkdir(parents=True, exist_ok=True)
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
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        logger.error(
            "Failed to write profile fontconfig; "
            "falling back to the system font configuration"
        )
        return None
    return target
