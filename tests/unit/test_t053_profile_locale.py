"""t053 AC-001/AC-002/AC-004/AC-005: Profile defaults and locale/timezone rules.

- New profiles default humanize/portable_cookies to True; every other
  advanced option keeps its previous default (pinned by test).
- locale converges to the zh-CN/en-US enum; timezone must be a valid IANA
  name or null.  The API rejects anything else with a field-level error.
- Timezone -> locale rule: Chinese-region timezones map to zh-CN, all
  others to en-US, empty timezone keeps the current value (None).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cbrowser.domain.models import (
    ProfileConfig,
    ProfileCreateRequest,
    ProfileUpdateRequest,
)
from cbrowser.domain.profile_locale import (
    CHINESE_REGION_TIMEZONES,
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    is_valid_timezone,
    locale_for_timezone,
    validate_timezone,
)


def test_chinese_region_timezones_map_to_zh_cn() -> None:
    assert CHINESE_REGION_TIMEZONES == frozenset(
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
    for tz in sorted(CHINESE_REGION_TIMEZONES):
        assert locale_for_timezone(tz) == "zh-CN"


def test_other_timezones_map_to_en_us() -> None:
    for tz in (
        "America/New_York",
        "America/Los_Angeles",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Tokyo",
        "Asia/Seoul",
        "Australia/Sydney",
        "UTC",
        "Etc/UTC",
    ):
        assert locale_for_timezone(tz) == "en-US"


def test_empty_timezone_keeps_current_value() -> None:
    assert locale_for_timezone(None) is None
    assert locale_for_timezone("") is None


def test_supported_locales_are_exactly_zh_cn_and_en_us() -> None:
    assert SUPPORTED_LOCALES == ("zh-CN", "en-US")
    assert DEFAULT_LOCALE == "en-US"


@pytest.mark.parametrize(
    "tz",
    [
        "Asia/Shanghai",
        "America/New_York",
        "Europe/London",
        "UTC",
        "Etc/UTC",
        "Australia/Sydney",
    ],
)
def test_valid_timezones_accepted(tz: str) -> None:
    assert is_valid_timezone(tz) is True


@pytest.mark.parametrize(
    "tz",
    ["Mars/Olympus", "Not/AZone", "Asia/NotACity", "", " ", "GMT+25"],
)
def test_invalid_timezones_rejected(tz: str) -> None:
    assert is_valid_timezone(tz) is False


def test_new_profile_defaults() -> None:
    config = ProfileConfig(name="Defaults")
    assert config.humanize is True
    assert config.portable_cookies is True
    # Every other advanced option keeps its previous default.
    assert config.transparent_proxy is False
    assert config.auto_launch is False
    assert config.allow_3p_cookies is True
    assert config.set_google_default is True
    assert config.clipboard_sync is True
    assert config.restore_session is True
    assert config.capture_preview is True
    assert config.geoip is True
    assert config.human_preset == "default"


def test_create_request_defaults() -> None:
    req = ProfileCreateRequest(name="Defaults")
    assert req.humanize is True
    assert req.portable_cookies is True
    assert req.transparent_proxy is False
    assert req.auto_launch is False
    assert req.allow_3p_cookies is True
    assert req.set_google_default is True
    assert req.clipboard_sync is True
    assert req.restore_session is True
    assert req.capture_preview is True
    assert req.geoip is True
    assert req.locale == "en-US"
    assert req.timezone is None


def test_create_request_rejects_other_locales() -> None:
    for bad in ("en-GB", "en", "zh", "fr-FR", "ja-JP", "zh-Hans"):
        with pytest.raises(ValidationError) as excinfo:
            ProfileCreateRequest(name="Bad", locale=bad)
        assert "locale" in str(excinfo.value)


def test_create_request_accepts_both_supported_locales() -> None:
    assert ProfileCreateRequest(name="Zh", locale="zh-CN").locale == "zh-CN"
    assert ProfileCreateRequest(name="En", locale="en-US").locale == "en-US"


def test_create_request_rejects_invalid_timezone() -> None:
    with pytest.raises(ValidationError) as excinfo:
        ProfileCreateRequest(name="Bad", timezone="Mars/Olympus")
    assert "timezone" in str(excinfo.value)


def test_create_request_accepts_valid_timezone() -> None:
    req = ProfileCreateRequest(name="Ok", timezone="Asia/Shanghai")
    assert req.timezone == "Asia/Shanghai"


def test_update_request_rejects_invalid_locale_and_timezone() -> None:
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(locale="en-GB")
    with pytest.raises(ValidationError):
        ProfileUpdateRequest(timezone="Not/AZone")
    assert ProfileUpdateRequest(locale="zh-CN").locale == "zh-CN"
    assert ProfileUpdateRequest(timezone="Europe/London").timezone == "Europe/London"
    assert ProfileUpdateRequest(locale=None).locale is None
    assert ProfileUpdateRequest(timezone=None).timezone is None


def test_domain_config_rejects_invalid_locale_and_timezone() -> None:
    with pytest.raises(ValidationError):
        ProfileConfig(name="Bad", locale="en-GB")
    with pytest.raises(ValidationError):
        ProfileConfig(name="Bad", timezone="Mars/Olympus")
    assert ProfileConfig(name="Ok", locale="zh-CN").locale == "zh-CN"
    assert ProfileConfig(name="Ok", timezone="Asia/Taipei").timezone == "Asia/Taipei"
    # Legacy nulls still load: existing stored values are unchanged.
    assert ProfileConfig(name="Legacy", locale=None).locale is None
    assert ProfileConfig(name="Legacy", timezone=None).timezone is None


@pytest.mark.asyncio
async def test_existing_profile_values_unchanged_by_upgrade(db_context) -> None:
    """AC-002: an explicitly stored False stays False after the default flip."""
    from cbrowser.adapters.database.repository import ProfileRepository

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    legacy = await repo.create_profile(
        ProfileConfig(name="Legacy", humanize=False, portable_cookies=False)
    )
    assert legacy.config.humanize is False
    assert legacy.config.portable_cookies is False
    reloaded = await repo.get_profile(legacy.id)
    assert reloaded is not None
    assert reloaded.config.humanize is False
    assert reloaded.config.portable_cookies is False


@pytest.mark.asyncio
async def test_new_profile_stored_with_new_defaults(db_context) -> None:
    from cbrowser.adapters.database.repository import ProfileRepository

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    profile = await repo.create_profile(ProfileConfig(name="New"))
    assert profile.config.humanize is True
    assert profile.config.portable_cookies is True
    assert profile.config.locale is None


def test_empty_timezone_means_unset_everywhere() -> None:
    """t053_code_f002: "" is "unset" (follow the egress IP), not an error.

    ``is_valid_timezone`` still answers the narrower "is this an IANA
    name" question ("" is not a name), but validation and the link rule
    both treat "" as unset: ``validate_timezone("")`` normalizes to
    ``None`` and every DTO stores ``None`` for it.
    """
    assert validate_timezone("") is None
    assert validate_timezone(None) is None
    assert validate_timezone("Asia/Shanghai") == "Asia/Shanghai"
    assert ProfileCreateRequest(name="Empty", timezone="").timezone is None
    assert ProfileUpdateRequest(timezone="").timezone is None
    assert ProfileConfig(name="Empty", timezone="").timezone is None
    # The link rule already agreed; keep it pinned alongside validation.
    assert locale_for_timezone("") is None


@pytest.mark.asyncio
async def test_stored_empty_timezone_row_loads_as_unset(db_context) -> None:
    """t053_code_f002: a legacy row that stored "" still loads (as unset)."""
    from cbrowser.adapters.database.models import ProfileModel
    from cbrowser.adapters.database.repository import ProfileRepository

    _engine, session_maker = db_context
    repo = ProfileRepository(session_maker)
    profile = await repo.create_profile(
        ProfileConfig(name="LegacyEmpty", timezone=None)
    )
    async with session_maker() as session:
        row = await session.get(ProfileModel, profile.id)
        assert row is not None
        row.timezone = ""
        await session.commit()
    reloaded = await repo.get_profile(profile.id)
    assert reloaded is not None
    assert reloaded.config.timezone is None
    assert reloaded.config.locale is None
