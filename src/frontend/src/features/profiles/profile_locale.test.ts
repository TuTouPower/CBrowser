import { describe, expect, it } from "vitest";
import {
  CHINESE_REGION_TIMEZONES,
  COMMON_TIMEZONES,
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  filterTimezones,
  getTimezones,
  localeForTimezone,
} from "./profile_locale";

describe("profile locale rules (t053)", () => {
  it("supports exactly zh-CN and en-US, defaulting to en-US", () => {
    expect(SUPPORTED_LOCALES).toEqual(["zh-CN", "en-US"]);
    expect(DEFAULT_LOCALE).toBe("en-US");
  });

  it("maps the Chinese-region timezone set to zh-CN", () => {
    expect([...CHINESE_REGION_TIMEZONES].sort()).toEqual([
      "Asia/Chongqing",
      "Asia/Harbin",
      "Asia/Hong_Kong",
      "Asia/Macau",
      "Asia/Shanghai",
      "Asia/Taipei",
      "Asia/Urumqi",
    ]);
    for (const zone of CHINESE_REGION_TIMEZONES) {
      expect(localeForTimezone(zone)).toBe("zh-CN");
    }
  });

  it("maps every other timezone to en-US", () => {
    for (const zone of [
      "America/New_York",
      "America/Los_Angeles",
      "Europe/London",
      "Europe/Berlin",
      "Asia/Tokyo",
      "Asia/Seoul",
      "Australia/Sydney",
      "UTC",
    ]) {
      expect(localeForTimezone(zone)).toBe("en-US");
    }
  });

  it("keeps the current language when the timezone is empty", () => {
    expect(localeForTimezone(null)).toBeNull();
    expect(localeForTimezone(undefined)).toBeNull();
    expect(localeForTimezone("")).toBeNull();
  });

  it("lists all IANA timezones with the common ones pinned first", () => {
    const zones = getTimezones();
    expect(zones.length).toBeGreaterThan(400);
    expect(zones).toContain("Asia/Shanghai");
    expect(zones).toContain("America/New_York");
    expect(zones).toContain("Europe/London");
    expect(zones.slice(0, COMMON_TIMEZONES.length)).toEqual([
      ...COMMON_TIMEZONES,
    ]);
  });

  it("filters by substring and keeps common zones first", () => {
    const matches = filterTimezones("shang");
    expect(matches).toContain("Asia/Shanghai");
    expect(matches).not.toContain("Europe/London");
    expect(matches[0]).toBe("Asia/Shanghai");

    const all = filterTimezones("");
    expect(all.length).toBeGreaterThan(400);
    expect(filterTimezones("europe/lond")).toEqual(["Europe/London"]);
  });
});
