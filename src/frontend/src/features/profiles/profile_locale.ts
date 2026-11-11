/** Profile locale and timezone rules (t053).

Mirrors the backend domain module `cbrowser/domain/profile_locale.py`:
the same Chinese-region timezone set and the same timezone -> locale
rule. The frontend table and the backend table are kept in agreement by
the unit tests on both sides (`profile_locale.test.ts` /
`test_t053_profile_locale.py`).
*/

export const SUPPORTED_LOCALES = ["zh-CN", "en-US"] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = "en-US";

export const CHINESE_REGION_TIMEZONES: ReadonlySet<string> = new Set([
  "Asia/Shanghai",
  "Asia/Chongqing",
  "Asia/Urumqi",
  "Asia/Harbin",
  "Asia/Hong_Kong",
  "Asia/Macau",
  "Asia/Taipei",
]);

/** Timezones shown first in the picker, in display order. */
export const COMMON_TIMEZONES: readonly string[] = [
  "Asia/Shanghai",
  "Asia/Taipei",
  "Asia/Hong_Kong",
  "Asia/Tokyo",
  "Asia/Seoul",
  "Asia/Singapore",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Australia/Sydney",
  "UTC",
];

export function localeForTimezone(
  timezone: string | null | undefined,
): SupportedLocale | null {
  if (timezone == null || timezone === "") {
    return null;
  }
  return CHINESE_REGION_TIMEZONES.has(timezone) ? "zh-CN" : "en-US";
}

let cachedTimezones: readonly string[] | null = null;

/** All IANA timezones, common ones first. Falls back to the common list
 * when `Intl.supportedValuesOf` is unavailable. */
export function getTimezones(): readonly string[] {
  if (cachedTimezones !== null) {
    return cachedTimezones;
  }
  let all: string[] = [];
  try {
    const supported = (
      Intl as unknown as {
        supportedValuesOf?: (key: string) => string[];
      }
    ).supportedValuesOf;
    if (typeof supported === "function") {
      all = supported.call(Intl, "timeZone");
    }
  } catch {
    all = [];
  }
  if (all.length === 0) {
    cachedTimezones = COMMON_TIMEZONES;
    return cachedTimezones;
  }
  // The pinned list is authoritative for its own entries: a common zone
  // stays offered even when this ICU build omits it (e.g. "UTC").
  const seen = new Set(all);
  for (const zone of COMMON_TIMEZONES) {
    if (!seen.has(zone)) {
      seen.add(zone);
      all = [...all, zone];
    }
  }
  const common = COMMON_TIMEZONES.filter((zone) => all.includes(zone));
  const rest = all.filter((zone) => !COMMON_TIMEZONES.includes(zone));
  cachedTimezones = [...common, ...rest];
  return cachedTimezones;
}

/** Filter `getTimezones()` by a case-insensitive substring, keeping
 * common timezones first. An empty query returns the full list. */
export function filterTimezones(query: string): readonly string[] {
  const needle = query.trim().toLowerCase();
  const zones = getTimezones();
  if (needle === "") {
    return zones;
  }
  const common = COMMON_TIMEZONES.filter(
    (zone) =>
      zones.includes(zone) && zone.toLowerCase().includes(needle),
  );
  const rest = zones.filter(
    (zone) =>
      !COMMON_TIMEZONES.includes(zone) &&
      zone.toLowerCase().includes(needle),
  );
  return [...common, ...rest];
}
