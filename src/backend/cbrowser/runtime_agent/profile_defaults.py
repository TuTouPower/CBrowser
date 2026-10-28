"""Profile defaults initialization for CloakBrowser runtime.

Configures default browser profile settings (such as default search engine)
using the active Playwright BrowserContext without secondary launches,
preserving existing tabs, process PID, and user custom preferences.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from .event_storage import atomic_write_json

logger = logging.getLogger("cbrowser.runtime_agent.profile_defaults")

SEARCH_ENGINE_MARKER_FILE = ".cbrowser_search_engine.json"
MARKER_VERSION = 1

SEARCH_ENGINE_NAME = "Google"
SEARCH_ENGINE_KEYWORD = "google.com"
SEARCH_ENGINE_URL = "https://www.google.com/search?q=%s"

_ACTIVE_DEFAULT_JS = """async () => {
    const cr = await import('chrome://resources/js/cr.js');
    const l = await cr.sendWithPromise('getSearchEnginesList');
    const a = (l.defaults || []).find(e => e.default);
    return a ? {name: a.name, keyword: a.keyword} : null;
}"""

_CLICK_ADD_BUTTON_JS = """() => {
    let clicked = false;
    const walk = (root) => root.querySelectorAll('*').forEach(el => {
        if (el.shadowRoot) walk(el.shadowRoot);
        if (el.tagName === 'CR-BUTTON'
            && el.id === 'addSearchEngine') {
            el.click();
            clicked = true;
        }
    });
    walk(document);
    return clicked;
}"""

_IS_ADD_ACTION_ENABLED_JS = """() => {
    let enabled = false;
    const walk = (root) => root.querySelectorAll('*').forEach(el => {
        if (el.shadowRoot) walk(el.shadowRoot);
        if (el.tagName === 'CR-BUTTON'
            && el.id === 'actionButton'
            && el.closest('cr-dialog')) {
            enabled = !el.disabled;
        }
    });
    walk(document);
    return enabled;
}"""

_SUBMIT_ADD_ACTION_JS = """() => {
    let clicked = false;
    const walk = (root) => root.querySelectorAll('*').forEach(el => {
        if (el.shadowRoot) walk(el.shadowRoot);
        if (el.tagName === 'CR-BUTTON'
            && el.id === 'actionButton'
            && el.closest('cr-dialog')
            && !el.disabled) {
            el.click();
            clicked = true;
        }
    });
    walk(document);
    return clicked;
}"""

_MAKE_GOOGLE_DEFAULT_JS = """() => {
    const walk = (root, fn) => root.querySelectorAll('*').forEach(el => {
        if (el.shadowRoot) walk(el.shadowRoot, fn);
        fn(el);
    });

    let targetRow = null;
    walk(document, el => {
        if (el.tagName === 'SETTINGS-SEARCH-ENGINE-ENTRY') {
            if (el.shadowRoot
            && el.shadowRoot.textContent.includes('google.com')) {
                targetRow = el.shadowRoot;
            }
        } else if (el.classList
            && el.classList.contains('list-item')
            && el.textContent.includes('google.com')) {
            targetRow = el;
        }
    });
    if (!targetRow) return Promise.resolve(false);

    let menuBtn = null;
    walk(targetRow, el => {
        if (el.tagName === 'CR-ICON-BUTTON'
            && el.classList.contains('icon-more-vert')) {
            menuBtn = el;
        }
    });
    if (!menuBtn) {
        walk(targetRow, el => {
            if (el.tagName === 'CR-ICON-BUTTON'
            && /More actions/i.test(el.getAttribute('aria-label') || '')) {
                menuBtn = el;
            }
        });
    }
    if (!menuBtn) return Promise.resolve(false);
    menuBtn.click();

    return new Promise(resolve => setTimeout(() => {
        let makeBtn = null;
        // Specifically look for makeDefault button inside the open CR-ACTION-MENU
        walk(document, el => {
            if (el.tagName === 'CR-ACTION-MENU'
            && el.open) {
                const b = el.querySelector('button#makeDefault');
                if (b
            && !b.disabled) {
                    makeBtn = b;
                }
            }
        });
        if (!makeBtn) {
            walk(document, el => {
                if (el.tagName === 'BUTTON'
            && el.id === 'makeDefault'
            && !el.disabled) {
                    const parentMenu = el.closest('cr-action-menu');
                    if (!parentMenu || parentMenu.open) {
                        makeBtn = el;
                    }
                }
            });
        }
        if (!makeBtn) {
            walk(document, el => {
                if (el.tagName === 'BUTTON'
            && (/Make default/i.test(el.textContent)
                || /设为默认/i.test(el.textContent))
            && !el.disabled) {
                    makeBtn = el;
                }
            });
        }
        if (!makeBtn) {
            resolve(false);
        } else {
            makeBtn.click();
            resolve(true);
        }
    }, 350));
}"""


class ProfileDefaultsError(RuntimeError):
    """Raised when profile defaults setup fails deterministically."""


def _read_marker(marker_path: Path) -> dict[str, Any] | None:
    """Read and validate existing marker file.

    Returns the parsed dict if valid, None if file does not exist.
    Raises ProfileDefaultsError if file exists but is corrupted/invalid.
    """
    if not marker_path.exists():
        return None

    try:
        raw = marker_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Marker payload is not a JSON object")
        if type(data.get("version")) is not int or data["version"] != MARKER_VERSION:
            raise ValueError("Unsupported marker version")
        if type(data.get("google_default_applied")) is not bool:
            raise ValueError("Invalid marker completion flag")
        if data.get("engine_keyword") != SEARCH_ENGINE_KEYWORD:
            raise ValueError("Invalid marker engine")
        return data
    except Exception as exc:
        logger.error(
            "Corrupt or invalid search engine marker in %s: %s",
            marker_path.parent.name,
            type(exc).__name__,
        )
        raise ProfileDefaultsError(
            f"Corrupt search engine marker in {marker_path.name}"
        ) from None


async def initialize_profile_defaults(
    context: Any,
    user_data_dir: Path | str,
    *,
    set_google_default: bool,
) -> None:
    """Initialize profile defaults using the caller's active BrowserContext.

    Args:
        context: Active Playwright BrowserContext from launch_persistent_context_async.
        user_data_dir: Profile user data directory.
        set_google_default: When True, add Google and make it default.
                            When False, immediately no-op.

    Raises:
        ProfileDefaultsError: If marker is corrupt, or search engine UI operations fail.
    """
    if not set_google_default:
        return

    ud_path = Path(user_data_dir)
    marker_path = ud_path / SEARCH_ENGINE_MARKER_FILE

    existing_marker = _read_marker(marker_path)
    if existing_marker and existing_marker.get("google_default_applied"):
        return

    page = None
    try:
        page = await context.new_page()
        await page.goto("chrome://settings/searchEngines")
        await asyncio.sleep(1.5)

        active = await page.evaluate(_ACTIVE_DEFAULT_JS)
        if active and active.get("keyword") == SEARCH_ENGINE_KEYWORD:
            # Already default (e.g. user set it or previous session did without marker)
            marker_data = {
                "version": MARKER_VERSION,
                "google_default_applied": True,
                "engine_keyword": SEARCH_ENGINE_KEYWORD,
            }
            atomic_write_json(marker_path, marker_data)
            return

        # 1. Click Add button
        if not await page.evaluate(_CLICK_ADD_BUTTON_JS):
            raise ProfileDefaultsError("Failed to trigger Add search engine dialog")
        await asyncio.sleep(1.0)

        # 2. Fill dialog inputs via trusted locator fills
        try:
            await page.locator("cr-input#searchEngine input").first.fill(
                SEARCH_ENGINE_NAME
            )
            await page.locator("cr-input#keyword input").first.fill(
                SEARCH_ENGINE_KEYWORD
            )
            await page.locator("cr-input#queryUrl input").first.fill(SEARCH_ENGINE_URL)
        except Exception as exc:
            logger.error("Failed filling search engine inputs: %s", type(exc).__name__)
            raise ProfileDefaultsError(
                "Failed to fill Add search engine dialog fields"
            ) from None

        # 3. Wait for action button to become enabled
        enabled = False
        for _ in range(15):
            await asyncio.sleep(0.2)
            if await page.evaluate(_IS_ADD_ACTION_ENABLED_JS):
                enabled = True
                break
        if not enabled:
            raise ProfileDefaultsError(
                "Add search engine action button remained disabled"
            )

        # 4. Submit dialog
        if not await page.evaluate(_SUBMIT_ADD_ACTION_JS):
            raise ProfileDefaultsError("Failed to submit Add search engine dialog")
        await asyncio.sleep(1.0)

        # 5. Make Google default
        clicked_make_default = await page.evaluate(_MAKE_GOOGLE_DEFAULT_JS)
        if not clicked_make_default:
            raise ProfileDefaultsError(
                "Failed to trigger Make Default action for Google"
            )
        await asyncio.sleep(1.0)

        # 6. Verify default taken
        active_after = await page.evaluate(_ACTIVE_DEFAULT_JS)
        if not (active_after and active_after.get("keyword") == SEARCH_ENGINE_KEYWORD):
            raise ProfileDefaultsError(
                "Google was not verified as active default engine"
            )

        # 7. Write atomic marker with fsync
        marker_data = {
            "version": MARKER_VERSION,
            "google_default_applied": True,
            "engine_keyword": SEARCH_ENGINE_KEYWORD,
        }
        atomic_write_json(marker_path, marker_data)
        logger.info(
            "Successfully set Google as default search engine for profile %s",
            ud_path.name,
        )

    except ProfileDefaultsError:
        raise
    except Exception as exc:
        logger.error(
            "Default search engine initialization failed: %s", type(exc).__name__
        )
        raise ProfileDefaultsError("Search engine initialization failed") from None
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
