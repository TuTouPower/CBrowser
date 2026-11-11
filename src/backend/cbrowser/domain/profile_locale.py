"""Profile locale and timezone rules (t053).

The Profile language converges to exactly two values, ``zh-CN`` and
``en-US``.  A timezone maps to a language through the Chinese-region set
below; an empty timezone means "follow the egress IP" and leaves the
language at its current value (``en-US`` for a new Profile).

The rule lives here, in the backend domain, so the API, the Runner and
the frontend (which mirrors the same table, covered by its own tests)
cannot drift apart.
"""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

SUPPORTED_LOCALES: tuple[str, ...] = ("zh-CN", "en-US")
DEFAULT_LOCALE = "en-US"

CHINESE_REGION_TIMEZONES: frozenset[str] = frozenset(
    {
        "Asia/Shanghai",
        "Asia/Chongqing",
        "Asia/Urumqi",
        "Asia/Harbin",
        "Asia/Hong_Kong",
        "Asia/Macau",
        "Asia/Taipei",
    }
)


def locale_for_timezone(timezone: str | None) -> str | None:
    """Map a timezone to its language, or ``None`` when unset.

    Chinese-region timezones select ``zh-CN``; every other valid IANA
    timezone selects ``en-US``.  ``None`` (or empty) keeps the current
    language: the caller must not overwrite it.
    """
    if timezone is None or timezone == "":
        return None
    return "zh-CN" if timezone in CHINESE_REGION_TIMEZONES else "en-US"


@lru_cache(maxsize=1)
def _available_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(value: object) -> bool:
    """Return whether ``value`` is a usable IANA timezone name.

    This answers the narrow "is this a name" question: ``""`` is not a
    name and returns ``False``. Callers that accept "unset" must use
    :func:`validate_timezone`, which normalizes ``""`` to ``None``.
    """
    if not isinstance(value, str) or not value:
        return False
    if value in _available_timezones():
        return True
    # ``available_timezones`` omits a few legacy aliases that ZoneInfo
    # still resolves; accept anything ZoneInfo can load.
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def validate_timezone(value: str | None) -> str | None:
    """Pydantic validator: a legal IANA timezone, or ``None`` for auto.

    ``""`` means the same as ``None`` ("follow the egress IP", per the
    spec: timezone is a legal IANA timezone or empty), so it normalizes
    to ``None`` instead of failing validation. This keeps validation and
    the link rule in agreement — :func:`locale_for_timezone` already
    treated ``""`` as unset — and lets rows that stored ``""`` load.
    """
    if value is None or value == "":
        return None
    if not is_valid_timezone(value):
        raise ValueError(f"Invalid IANA timezone: {value!r}")
    return value


def validate_locale(value: str | None) -> str | None:
    """Pydantic validator: ``zh-CN`` / ``en-US``, or ``None`` for legacy."""
    if value is None:
        return None
    if value not in SUPPORTED_LOCALES:
        raise ValueError(
            "Unsupported locale: "
            f"{value!r}; expected one of {', '.join(SUPPORTED_LOCALES)}"
        )
    return value
