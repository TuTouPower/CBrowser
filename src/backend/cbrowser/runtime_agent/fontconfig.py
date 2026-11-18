"""Per-profile fontconfig generation with an explicit directory whitelist.

The Browser image keeps its base open-source fonts under
``/opt/cbrowser-base-fonts`` so that CloakBrowser's documented minimum
font packages are installed. Those fonts are Linux-flavoured (WenQuanYi,
Unifont, FreeFont, IPAGothic, Loma) and must NOT be visible to a
fingerprint Profile: plan 6.8 requires Linux-only fonts to be invisible
on both windows and macos platforms. The Supervisor mounts the bound
platform font set read-only under ``/run/cbrowser/fonts/{platform}/{set_id}``
and that set is the *only* directory a Profile's fontconfig whitelists.

t075: every Profile is bound to a verified platform font set by the
backend, so there is no unbound fallback any more — a missing binding
or an unusable set fails closed (``font_set_unavailable``) instead of
silently exposing the Linux base fonts. The system configuration is
never included.

Chinese-font exposure is governed by the Profile's explicit
``include_cjk_fonts`` switch, decoupled from locale (t075; the t053
locale rule is abolished): when the switch is off, the generated
config carries one ``<selectfont><rejectfont>`` rule per Chinese
language tag, so fonts whose coverage includes Chinese are invisible;
when it is on, no rejection is generated for any locale. The rule is
evaluated by fontconfig itself at scan time, so it applies to every
face of a ``.ttc`` collection. Fonts whose coverage declares no
Chinese tag (Latin, Japanese-only, Korean-only, ...) are untouched.
"""

from __future__ import annotations

import logging
from pathlib import Path
from xml.sax.saxutils import escape

from cbrowser.shared.atomic_write import atomic_write_text

logger = logging.getLogger("cbrowser.runtime_agent.fontconfig")

BASE_FONTS_DIR = Path("/opt/cbrowser-base-fonts")
FONT_SET_MOUNT_ROOT = Path("/run/cbrowser/fonts")
PROFILE_FONTCONFIG_FILENAME = "profile-fonts.conf"
FONT_SET_UNAVAILABLE = "font_set_unavailable"

# Fontconfig language tags whose presence in a font's coverage marks it
# as a Chinese font for the include_cjk_fonts split. Every face of the
# platform sets' Chinese fonts (Microsoft YaHei/SimSun, PingFang/
# Hiragino Sans GB/STHeiti, Songti, WenQuanYi) declares at least one of
# these.
CHINESE_LANG_TAGS: tuple[str, ...] = (
    "zh",
    "zh-cn",
    "zh-tw",
    "zh-hk",
    "zh-mo",
    "zh-sg",
)

DEFAULT_CACHE_DIR = Path("/tmp/cbrowser-fontconfig-cache")


class FontConfigUnavailableError(RuntimeError):
    """Fail closed when a bound Profile's fonts cannot be used.

    The reason is the fixed, non-sensitive string ``font_set_unavailable``:
    no font path or platform detail ever reaches the exception, a log line,
    or the reported runtime state. The Runner raises this instead of
    falling back to the system font configuration or the Linux base
    fonts, so a Profile never runs with the wrong fonts visible.
    """

    def __init__(self) -> None:
        super().__init__(FONT_SET_UNAVAILABLE)


def profile_font_dirs(platform: str, font_set_id: str | None) -> list[Path]:
    """Select the FONTCONFIG_FILE whitelist for a Profile.

    The bound platform font set is the only visible directory. An
    unbound Profile yields an empty whitelist: since t075 the backend
    guarantees a binding, so reaching launch unbound is a defect the
    Runner refuses (fail closed), never a base-fonts fallback.
    """
    if font_set_id:
        return [FONT_SET_MOUNT_ROOT / platform / font_set_id]
    return []


def build_fontconfig_xml(
    dirs: list[Path | str],
    include_cjk_fonts: bool = True,
    cache_dir: Path | str | None = None,
) -> str:
    """Render a fontconfig file that scans only ``dirs``.

    The system configuration is deliberately not included: doing so would
    re-expose every font under the default scan paths. An empty ``dirs``
    is valid and yields a config with no ``<dir>`` entries; callers decide
    which directories to whitelist via :func:`profile_font_dirs`.

    ``include_cjk_fonts=False`` appends one ``<rejectfont>`` rule per
    Chinese language tag, so fonts whose coverage includes Chinese are
    invisible to the Profile; ``True`` appends no rejection. ``cache_dir``
    overrides the default cache location (tests use an isolated
    directory).
    """
    lines = [
        '<?xml version="1.0"?>',
        '<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">',
        "<fontconfig>",
        f"  <cachedir>{escape(str(cache_dir or DEFAULT_CACHE_DIR))}</cachedir>",
    ]
    for directory in dirs:
        lines.append(f"  <dir>{escape(str(directory))}</dir>")
    if not include_cjk_fonts:
        for tag in CHINESE_LANG_TAGS:
            lines.extend(
                [
                    "  <selectfont>",
                    "    <rejectfont>",
                    "      <pattern>",
                    f'        <patelt name="lang"><string>{tag}</string></patelt>',
                    "      </pattern>",
                    "    </rejectfont>",
                    "  </selectfont>",
                ]
            )
    lines.append("</fontconfig>")
    return "\n".join(lines) + "\n"


def prepare_profile_fontconfig(
    run_dir: Path,
    dirs: list[Path | str],
    include_cjk_fonts: bool = True,
    cache_dir: Path | str | None = None,
) -> Path | None:
    """Write the profile fontconfig file into ``run_dir``.

    Any ``dirs`` value produces a file. Callers pass the bound platform
    set plus the Profile's CJK switch so the exposure split applies.
    Returns ``None`` only when generation fails; the Runner treats that
    as fatal (fail closed, A18). The file lands via the shared atomic
    write (cbrowser.shared.atomic_write).
    """
    target = run_dir / PROFILE_FONTCONFIG_FILENAME
    try:
        xml = build_fontconfig_xml(
            dirs, include_cjk_fonts=include_cjk_fonts, cache_dir=cache_dir
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, xml, mode=0o600)
    except (OSError, ValueError):
        logger.error(
            "Failed to write profile fontconfig; the caller decides "
            "whether to fail closed (bound font set) or fall back"
        )
        return None
    return target
