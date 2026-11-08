"""t041 AC-004 / AC-005 real-engine E2E: platform UA / Client Hints, fontconfig
whitelist isolation, and platform CJK / emoji rendering.

A browser-image container runs the real Linux arm64 Chromium 146 engine with
--fingerprint-platform=windows / macos. The host mounts the official Windows
font set extracted from the Microsoft evaluation ISO and the local macOS
system fonts as read-only platform sets. The generated FONTCONFIG_FILE
whitelists ONLY that platform set: base Linux-flavoured fonts stay in the
image for CloakBrowser's minimum install but are never visible to a
fingerprint Profile (plan 6.8 / user 2026-11-06 supervision).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from e2e_env import require_e2e_available, require_e2e_env


pytestmark = pytest.mark.serial
MAC_FONT_DIRS = (
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path(
        "/System/Library/AssetsV2/com_apple_MobileAsset_Font8/"
        "86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData"
    ),
)

PROBE_SCRIPT = '''"""t041 real-engine probe: UA/CH, platform font whitelist, CJK/emoji render."""
from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import threading
from pathlib import Path


ENGINE = "/data/engine-cache/chromium-146.0.7680.177.3/chrome"
LINUX_FONT_RE = re.compile(
    r"Liberation|Nimbus|DejaVu|URW|Standard Symbols|P052|C059|D050000L|Z003|"
    r"WenQuanYi|文泉驿|Unifont|FreeSans|FreeSerif|FreeMono|IPAGothic|IPA|"
    r"Loma|Noto Color Emoji",
    re.IGNORECASE,
)
FC = {
    "windows": "/tmp/fc_windows.conf",
    "macos": "/tmp/fc_macos.conf",
}
WHITELIST_XML = {
    "windows": """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <cachedir>/tmp/cbrowser-fontconfig-cache</cachedir>
  <dir>/probe_fonts/windows</dir>
</fontconfig>
""",
    "macos": """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <cachedir>/tmp/cbrowser-fontconfig-cache</cachedir>
  <dir>/probe_fonts/macos1</dir>
  <dir>/probe_fonts/macos2</dir>
  <dir>/probe_fonts/macos3</dir>
</fontconfig>
""",
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<!doctype html><title>probe</title><body>t041</body>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


BASIC_JS = """() => ({
  navigatorPlatform: navigator.platform,
  userAgent: navigator.userAgent,
  uaDataPlatform: navigator.userAgentData ? navigator.userAgentData.platform : null,
  isSecureContext: isSecureContext
})"""

HIGH_ENTROPY_JS = """async () => {
  if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) {
    return null;
  }
  try {
    return await navigator.userAgentData.getHighEntropyValues([
      "platform", "platformVersion", "architecture"
    ]);
  } catch (e) {
    return {error: String(e)};
  }
}"""

CANVAS_JS = """() => {
  const c = document.createElement('canvas');
  const ctx = c.getContext('2d');
  const w = (font, text) => { ctx.font = font; return ctx.measureText(text).width; };
  return {
    cjk: w('40px "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", monospace', '中文测试'),
    cjkMono: w('40px monospace', '中文测试'),
    emoji: w('40px "Segoe UI Emoji", "Apple Color Emoji", monospace', '😀'),
    emojiMono: w('40px monospace', '😀')
  };
}"""


def _probe_platform(platform: str, origin: str) -> dict:
    from playwright.sync_api import sync_playwright
    os.environ["FONTCONFIG_FILE"] = FC[platform]
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=ENGINE,
            headless=True,
            args=["--no-sandbox", f"--fingerprint-platform={platform}"],
        )
        try:
            page = browser.new_page()
            page.goto(origin, wait_until="domcontentloaded", timeout=20000)
            return {
                "basic": page.evaluate(BASIC_JS),
                "highEntropy": page.evaluate(HIGH_ENTROPY_JS),
                "canvas": page.evaluate(CANVAS_JS),
            }
        finally:
            browser.close()


def _fc_list(extra_env: dict) -> dict:
    env = dict(os.environ)
    env.pop("FONTCONFIG_FILE", None)
    env.update(extra_env)
    proc = subprocess.run(
        ["fc-list", ":", "family"],
        capture_output=True, text=True, env=env,
    )
    families = [line for line in proc.stdout.splitlines() if line.strip()]
    files_proc = subprocess.run(
        ["fc-list", "-f", "%{file}\\n"],
        capture_output=True, text=True, env=env,
    )
    files = [line for line in files_proc.stdout.splitlines() if line.strip()]
    return {
        "returncode": proc.returncode,
        "stderr": proc.stderr,
        "familyCount": len(families),
        "linuxHits": sum(1 for line in families if LINUX_FONT_RE.search(line)),
        "files": files,
    }


def _fc_match(family: str, extra_env: dict) -> str:
    env = dict(os.environ)
    env.pop("FONTCONFIG_FILE", None)
    env.update(extra_env)
    proc = subprocess.run(
        ["fc-match", "-f", "%{family}|%{file}", family],
        capture_output=True, text=True, env=env,
    )
    return proc.stdout.strip()


def main() -> None:
    result = {"engineExists": Path(ENGINE).is_file(), "platforms": {}, "fontconfig": {}, "fcMatch": {}}
    for platform, path in FC.items():
        Path(path).write_text(WHITELIST_XML[platform], encoding="utf-8")
    result["fontconfig"]["whitelistXml"] = WHITELIST_XML
    result["fontconfig"]["control"] = _fc_list({})
    for platform in ("windows", "macos"):
        result["fontconfig"][platform] = _fc_list({"FONTCONFIG_FILE": FC[platform]})

    families = {
        "windows": ("Microsoft YaHei", "SimSun", "Segoe UI Emoji"),
        "macos": ("PingFang SC", "Hiragino Sans GB", "Apple Color Emoji"),
    }
    for platform, names in families.items():
        result["fcMatch"][platform] = {
            name: _fc_match(name, {"FONTCONFIG_FILE": FC[platform]})
            for name in names
        }

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_address[1]}/"
    try:
        for platform in ("windows", "macos"):
            try:
                result["platforms"][platform] = _probe_platform(platform, origin)
            except Exception as exc:
                result["platforms"][platform] = {"error": f"{type(exc).__name__}: {exc}"}
    finally:
        server.shutdown()
        server.server_close()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
'''


def _resolve_engine_cache() -> Path:
    return Path(os.environ["CBROWSER_RUNTIME_ENGINE_CACHE"])


def _image_present(image: str) -> bool:
    """True when the browser runtime image is present locally."""
    import docker

    client = docker.from_env()
    try:
        client.images.get(image)
        return True
    except Exception:  # noqa: BLE001 - any lookup failure is a missing prerequisite
        return False
    finally:
        client.close()


@pytest.fixture(scope="module")
def probe_result(tmp_path_factory: pytest.TempPathFactory) -> dict:
    env = require_e2e_env("CBROWSER_RUNTIME_TEST_IMAGE")
    image = env["CBROWSER_RUNTIME_TEST_IMAGE"]
    fonts_env = require_e2e_env(
        "CBROWSER_E2E_FONTS_DIR",
        "CBROWSER_RUNTIME_ENGINE_CACHE",
        paths=("CBROWSER_E2E_FONTS_DIR", "CBROWSER_RUNTIME_ENGINE_CACHE"),
        docker=True,
        fonts_platform="windows",
    )
    windows_fonts = Path(fonts_env["_fonts_dir"])
    engine_cache = _resolve_engine_cache()

    missing_mac = [str(p) for p in MAC_FONT_DIRS if not p.is_dir()]
    require_e2e_available(
        not missing_mac,
        "macOS system font directories missing: " + ", ".join(missing_mac),
    )
    require_e2e_available(
        _image_present(image),
        f"browser runtime image not present locally: {image}",
    )

    script_dir = tmp_path_factory.mktemp("t041-probe")
    (script_dir / "probe.py").write_text(PROBE_SCRIPT, encoding="utf-8")
    mounts = [
        "-v", f"{engine_cache}:/data/engine-cache:ro",
        "-v", f"{script_dir}:/probe:ro",
        "-v", f"{windows_fonts}:/probe_fonts/windows:ro",
        "-v", f"{MAC_FONT_DIRS[0]}:/probe_fonts/macos1:ro",
        "-v", f"{MAC_FONT_DIRS[1]}:/probe_fonts/macos2:ro",
        "-v", f"{MAC_FONT_DIRS[2]}:/probe_fonts/macos3:ro",
    ]
    proc = subprocess.run(
        ["docker", "run", "--rm", "--entrypoint", "python3", *mounts,
         image, "/probe/probe.py"],
        capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"probe container failed (rc={proc.returncode}); "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    try:
        payload = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"probe stdout is not pure JSON ({exc}); "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
        ) from exc
    assert isinstance(payload, dict)
    return payload


def test_real_engine_platform_ua_and_client_hints_are_consistent(probe_result: dict) -> None:
    """AC-004: each platform reports a mutually consistent navigator.platform, UA and UA-CH."""
    assert probe_result["engineExists"] is True
    platforms = probe_result["platforms"]
    expected = {
        "windows": {
            "navigatorPlatform": "Win32",
            "uaSubstring": "Windows NT",
            "uaDataPlatform": "Windows",
            "chPlatform": "Windows",
            "platformVersion": "19.0.0",
        },
        "macos": {
            "navigatorPlatform": "MacIntel",
            "uaSubstring": "Macintosh",
            "uaDataPlatform": "macOS",
            "chPlatform": "macOS",
            "platformVersion": "15.2.0",
        },
    }
    for name, exp in expected.items():
        assert name in platforms, f"missing {name} probe result: {platforms}"
        entry = platforms[name]
        assert "error" not in entry, f"{name} probe error: {entry}"
        basic = entry["basic"]
        high_entropy = entry["highEntropy"]
        assert basic["isSecureContext"] is True
        assert basic["navigatorPlatform"] == exp["navigatorPlatform"]
        assert exp["uaSubstring"] in basic["userAgent"]
        assert basic["uaDataPlatform"] == exp["uaDataPlatform"]
        assert high_entropy is not None and "error" not in high_entropy
        assert high_entropy.get("platform") == exp["chPlatform"]
        assert high_entropy.get("platformVersion") == exp["platformVersion"]


def test_fontconfig_whitelist_hides_all_linux_fonts(probe_result: dict) -> None:
    """AC-005 / AC-008: the FONTCONFIG_FILE exposes only the bound platform
    font set. Neither system Linux fonts nor the Linux-flavoured base open
    source fonts (WenQuanYi, Unifont, FreeFont, IPAGothic, Loma) may be
    visible to a windows or macos fingerprint Profile."""
    fontconfig = probe_result["fontconfig"]
    for platform in ("windows", "macos"):
        xml = fontconfig["whitelistXml"][platform]
        assert "/opt/cbrowser-base-fonts" not in xml
        assert "<include" not in xml
        assert "/etc/fonts/fonts.conf" not in xml
        assert "<dir>/probe_fonts/" in xml
        entry = fontconfig[platform]
        assert entry["returncode"] == 0
        assert entry["linuxHits"] == 0, (
            f"{platform} whitelist exposed Linux fonts: {entry['linuxHits']}"
        )
        assert entry["files"], f"{platform} whitelist exposed no fonts"
        assert all(
            path.startswith("/probe_fonts/") for path in entry["files"]
        ), f"non-platform font leaked into {platform} whitelist: {entry['files']}"
    control = fontconfig["control"]
    assert control["returncode"] == 0
    assert control["linuxHits"] > 0
    assert any(
        path.startswith("/usr/share/fonts/") for path in control["files"]
    ), "control run should expose system Linux fonts"


def test_platform_fonts_render_cjk_and_emoji(probe_result: dict) -> None:
    """AC-005: CJK resolves to the platform font (YaHei/SimSun or
    PingFang/Hiragino) and emoji has a platform font or a sane fallback in
    the real Chromium 146 engine."""
    expected_root = {
        "windows": "/probe_fonts/windows/",
        "macos": "/probe_fonts/macos",
    }
    for platform, root in expected_root.items():
        matches = probe_result["fcMatch"][platform]
        cjk_names = ("Microsoft YaHei", "SimSun") if platform == "windows" else (
            "PingFang SC", "Hiragino Sans GB"
        )
        assert any(
            root in matches[name] for name in cjk_names
        ), f"{platform} CJK resolved to a non-platform font: {matches}"
        emoji_name = "Segoe UI Emoji" if platform == "windows" else "Apple Color Emoji"
        assert matches[emoji_name], f"{platform} emoji has no font match"
        canvas = probe_result["platforms"][platform]["canvas"]
        assert canvas["cjk"] > 0, f"{platform} CJK did not render"
        assert canvas["emoji"] > 0, f"{platform} emoji did not render"
