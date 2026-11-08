from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import vendor_selkies_web as vendor_module

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WHEEL_CACHE = REPO_ROOT / '.scratch' / 'selkies_wheels'
MANIFEST_PATH = REPO_ROOT / 'config' / 'selkies' / 'selkies_web_sha256.txt'


def _pinned_wheel() -> Path:
    cache = Path(
        os.environ.get('CBROWSER_SELKIES_WHEEL_CACHE', str(DEFAULT_WHEEL_CACHE))
    )
    return cache / vendor_module.PINNED_WHEEL_FILENAME


def _forbid_public_download(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def _download(*args, **kwargs):
        calls.append('download_wheel')
        raise AssertionError('public wheel download attempted')

    def _urlopen(*args, **kwargs):
        calls.append('urlopen')
        raise AssertionError('public network access attempted')

    monkeypatch.setattr(vendor_module, 'download_wheel', _download)
    monkeypatch.setattr(vendor_module.urllib.request, 'urlopen', _urlopen)
    return calls


def test_cached_wheel_never_triggers_public_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _pinned_wheel()
    assert wheel.is_file(), f'local Selkies wheel cache missing: {wheel}'
    calls = _forbid_public_download(monkeypatch)
    dest = tmp_path / 'selkies'

    vendor_module.vendor_selkies_web(
        dest_dir=dest,
        wheel_path=wheel,
        cache_dir=tmp_path / 'cache',
        manifest_path=MANIFEST_PATH,
        inject_adapter=False,
        allow_download=False,
    )

    assert calls == []
    assert (dest / 'index.html').is_file()


def test_missing_local_wheel_fails_closed_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _forbid_public_download(monkeypatch)
    missing = tmp_path / 'missing.whl'
    cache = tmp_path / 'cache'
    cache.mkdir()

    with pytest.raises(RuntimeError, match='download disabled') as exc:
        vendor_module.vendor_selkies_web(
            dest_dir=tmp_path / 'selkies',
            wheel_path=missing,
            cache_dir=cache,
            manifest_path=MANIFEST_PATH,
            inject_adapter=False,
            allow_download=False,
        )

    message = str(exc.value)
    assert str(missing) in message
    assert str(cache / vendor_module.PINNED_WHEEL_FILENAME) in message
    assert calls == []
