import type { TranslationKey } from "../i18n";
import type { StatusTone } from "./ui/StatusBadge";

/**
 * t079: single source of presentation semantics.
 *
 * Business concepts (environment runtime state, proxy probe outcome,
 * region identity) are mapped to localized labels and visual tones in
 * exactly one place. Surfaces never render raw machine values (enum
 * states, probe error codes, country codes as letter badges); the raw
 * machine value stays available for diagnostics (API payloads, titles)
 * but is never the primary user-facing text.
 */

export interface StatusDescriptor {
  tone: StatusTone;
  label: TranslationKey;
}

const ENVIRONMENT_STATUS: Record<string, StatusDescriptor> = {
  running: { tone: "running", label: "statusRunning" },
  starting: { tone: "transition", label: "statusStarting" },
  stopping: { tone: "transition", label: "statusStopping" },
  error: { tone: "error", label: "statusError" },
  stopped: { tone: "stopped", label: "statusStopped" },
};

const ENVIRONMENT_STATUS_UNKNOWN: StatusDescriptor = {
  tone: "stopped",
  label: "statusUnknown",
};

/**
 * Environment runtime state → presentation. A missing or out-of-enum
 * observed state is presented as an explicit "unknown", never silently
 * disguised as "stopped" (t079 AC-002).
 */
export function environmentStatusDescriptor(
  observed: string | null | undefined,
): StatusDescriptor {
  if (observed == null) return ENVIRONMENT_STATUS_UNKNOWN;
  return ENVIRONMENT_STATUS[observed] ?? ENVIRONMENT_STATUS_UNKNOWN;
}

const PROXY_PROBE_ERROR_KEYS: Record<string, TranslationKey> = {
  probe_failed: "proxyProbeFailed",
  probe_bad_response: "proxyErrorProbeBadResponse",
  supervisor_unavailable: "proxyErrorSupervisorUnavailable",
  proxy_credentials_unavailable: "proxyErrorCredentialsUnavailable",
  echo_unreachable: "proxyErrorEchoUnreachable",
  echo_proxy_unsupported: "proxyErrorEchoProxyUnsupported",
  invalid_echo_response: "proxyErrorInvalidEchoResponse",
  geoip_lookup_failed: "proxyErrorGeoipLookupFailed",
  proxy_auth_failed: "proxyErrorAuthFailed",
  proxy_unreachable: "proxyErrorUnreachable",
};

/**
 * Proxy probe error code → localized explanation key. Known codes get
 * an accurate description; a missing or unknown code falls back to the
 * generic probe-failure label, so the main status text never leaks a
 * raw machine code (t079 AC-001). The code itself remains the stable
 * diagnostic identifier in storage and API payloads.
 */
export function proxyProbeErrorLabelKey(
  code: string | null | undefined,
): TranslationKey {
  if (code == null) return "proxyProbeFailed";
  return PROXY_PROBE_ERROR_KEYS[code] ?? "proxyProbeFailed";
}

/** Valid ISO 3166-1 alpha-2 shape (the region identity format). */
export function isRegionCode(code: string | null | undefined): boolean {
  return typeof code === "string" && /^[A-Za-z]{2}$/.test(code);
}

const REGION_NAMES_EN = new Intl.DisplayNames(["en"], { type: "region" });
const regionNamesByLocale = new Map<string, Intl.DisplayNames>();

function regionNames(locale: string): Intl.DisplayNames {
  let names = regionNamesByLocale.get(locale);
  if (!names) {
    names = new Intl.DisplayNames([locale], { type: "region" });
    regionNamesByLocale.set(locale, names);
  }
  return names;
}

/**
 * A code is a *known* region only when the canonical CLDR table has a
 * real name for it. Format-valid but unassigned codes and unknown
 * sentinels (XX, ZZ, AA, …) resolve to the code itself or to
 * "Unknown Region" in CLDR and are treated as unknown, so they never
 * receive a fabricated flag (t079 AC-005).
 */
export function isKnownRegion(code: string | null | undefined): boolean {
  if (!isRegionCode(code)) return false;
  const upper = code!.toUpperCase();
  try {
    const name = REGION_NAMES_EN.of(upper);
    return name !== undefined && name !== upper && name !== "Unknown Region";
  } catch {
    return false;
  }
}

/**
 * Flag emoji for a known region; `null` for anything else, so an
 * unknown code is never dressed up with a fabricated flag (AC-005).
 */
export function regionFlagEmoji(code: string | null | undefined): string | null {
  if (!isKnownRegion(code)) return null;
  const upper = code!.toUpperCase();
  return String.fromCodePoint(
    ...[...upper].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65),
  );
}

/** Canonical English region name (the country sort key, AC-004). */
export function regionEnglishName(code: string): string {
  const upper = code.toUpperCase();
  if (!isKnownRegion(upper)) return upper;
  try {
    return REGION_NAMES_EN.of(upper) ?? upper;
  } catch {
    return upper;
  }
}

/** Localized region name for presentation; falls back to the code. */
export function regionDisplayName(code: string, locale: string): string {
  const upper = code.toUpperCase();
  if (!isKnownRegion(upper)) return upper;
  try {
    return regionNames(locale).of(upper) ?? upper;
  } catch {
    return upper;
  }
}

const NAME_COLLATOR = new Intl.Collator("en", {
  sensitivity: "base",
  numeric: true,
});

/**
 * Deterministic name ordering (AC-004): one CLDR collator for every
 * script — Latin names order A–Z, non-Latin names order by the
 * collator's locale rules for their script — with a code-point
 * tie-break so equal-folded names keep a stable, input-independent
 * order. Never orders by flag, code, or upstream/interface order.
 */
export function compareNames(a: string, b: string): number {
  const folded = NAME_COLLATOR.compare(a, b);
  if (folded !== 0) return folded;
  return a < b ? -1 : a > b ? 1 : 0;
}

export interface CountryCandidate {
  country_code: string;
  country_name?: string | null;
  cities: string[];
}

/**
 * Country candidates sorted by canonical English name (A–Z), deduped
 * by country code (identity is the code; the first range wins). The
 * "all" entry is added by the caller and stays first (AC-004).
 */
export function sortCountryCandidates<T extends CountryCandidate>(
  ranges: readonly T[],
): T[] {
  const byCode = new Map<string, T>();
  for (const range of ranges) {
    const code = range.country_code.toUpperCase();
    if (!byCode.has(code)) byCode.set(code, range);
  }
  // Resolve each sort key once instead of per comparison.
  const sortKeys = new Map<string, string>();
  for (const code of byCode.keys()) {
    sortKeys.set(code, regionEnglishName(code));
  }
  return [...byCode.values()].sort((a, b) => {
    const byName = compareNames(
      sortKeys.get(a.country_code.toUpperCase())!,
      sortKeys.get(b.country_code.toUpperCase())!,
    );
    return byName !== 0
      ? byName
      : compareNames(a.country_code, b.country_code);
  });
}

/** City candidates deduped and sorted by the shared name rule. */
export function sortCityCandidates(cities: Iterable<string>): string[] {
  return [...new Set(cities)].sort(compareNames);
}
