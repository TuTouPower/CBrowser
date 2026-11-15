/** Profile locale, timezone, proxy, and font-set auto-alignment rules (t053+).

Mirrors the backend domain module `cbrowser/domain/profile_locale.py`:
the same Chinese-region timezone set and the same timezone -> locale
rule, plus automatic alignment between proxy location, timezone,
language, and platform font sets.
*/

import type { FontSetInfo } from "../../shared/api/types";

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

export function timezoneForLocale(
  locale: string | null | undefined,
  currentTimezone: string | null | undefined,
): string | null {
  if (locale === "zh-CN") {
    if (currentTimezone && CHINESE_REGION_TIMEZONES.has(currentTimezone)) {
      return currentTimezone;
    }
    return "Asia/Shanghai";
  }
  if (locale === "en-US") {
    if (currentTimezone && !CHINESE_REGION_TIMEZONES.has(currentTimezone)) {
      return currentTimezone;
    }
    return "America/Los_Angeles";
  }
  return currentTimezone ?? null;
}

export function timezoneForProxy(
  proxy:
    | {
        country_code?: string | null;
        region_label?: string | null;
        name?: string | null;
      }
    | null
    | undefined,
): string | null {
  if (!proxy) return null;
  const cc = (proxy.country_code ?? "").trim().toUpperCase();
  const text = `${proxy.region_label ?? ""} ${proxy.name ?? ""}`.toLowerCase();

  if (text.includes("new york") || text.includes("ny") || text.includes("纽约") || text.includes("美东")) {
    return "America/New_York";
  }
  if (text.includes("chicago") || text.includes("芝加哥") || text.includes("美中")) {
    return "America/Chicago";
  }
  if (text.includes("los angeles") || text.includes("california") || text.includes("la") || text.includes("洛杉矶") || text.includes("美西")) {
    return "America/Los_Angeles";
  }
  if (text.includes("london") || text.includes("伦敦") || text.includes("英国") || cc === "GB" || cc === "UK") {
    return "Europe/London";
  }
  if (text.includes("frankfurt") || text.includes("berlin") || text.includes("法兰克福") || text.includes("德国") || cc === "DE") {
    return "Europe/Berlin";
  }
  if (text.includes("paris") || text.includes("巴黎") || text.includes("法国") || cc === "FR") {
    return "Europe/Paris";
  }
  if (text.includes("singapore") || text.includes("新加坡") || cc === "SG") {
    return "Asia/Singapore";
  }
  if (text.includes("hong kong") || text.includes("香港") || cc === "HK") {
    return "Asia/Hong_Kong";
  }
  if (text.includes("taipei") || text.includes("taiwan") || text.includes("台北") || text.includes("台湾") || cc === "TW") {
    return "Asia/Taipei";
  }
  if (text.includes("macau") || text.includes("澳门") || cc === "MO") {
    return "Asia/Macau";
  }
  if (text.includes("shanghai") || text.includes("beijing") || text.includes("上海") || text.includes("北京") || text.includes("中国") || cc === "CN") {
    return "Asia/Shanghai";
  }
  if (text.includes("tokyo") || text.includes("东京") || text.includes("日本") || cc === "JP") {
    return "Asia/Tokyo";
  }
  if (text.includes("seoul") || text.includes("首尔") || text.includes("韩国") || cc === "KR") {
    return "Asia/Seoul";
  }
  if (text.includes("sydney") || text.includes("悉尼") || text.includes("澳大利亚") || cc === "AU") {
    return "Australia/Sydney";
  }
  if (cc === "US") {
    return "America/Los_Angeles";
  }
  return null;
}

export function selectFontSetForLocaleAndPlatform(
  fontSets: readonly FontSetInfo[],
  platform: "windows" | "macos",
  locale: string | null | undefined,
  defaultFontSetId: Record<string, string | null | undefined>,
): string | null {
  const candidates = fontSets.filter(
    (item) => item.platform === platform && item.integrity.ok,
  );
  if (candidates.length === 0) {
    return defaultFontSetId[platform] ?? null;
  }
  if (locale === "zh-CN") {
    const cjk = candidates.find((item) => {
      const hay = `${item.set_id} ${item.source ?? ""} ${item.source_version ?? ""}`.toLowerCase();
      return hay.includes("cjk") || hay.includes("office") || hay.includes("zh") || hay.includes("yahei") || hay.includes("pingfang");
    });
    if (cjk) return cjk.set_id;
  } else if (locale === "en-US") {
    const core = candidates.find((item) => {
      const hay = `${item.set_id} ${item.source ?? ""} ${item.source_version ?? ""}`.toLowerCase();
      return !hay.includes("cjk") && !hay.includes("office");
    });
    if (core) return core.set_id;
  }
  return defaultFontSetId[platform] ?? candidates[0]?.set_id ?? null;
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
  return zones.filter((zone) => zone.toLowerCase().includes(needle));
}
