import { describe, expect, it } from "vitest";
import {
  compareNames,
  environmentStatusDescriptor,
  isKnownRegion,
  isRegionCode,
  proxyProbeErrorLabelKey,
  regionEnglishName,
  regionFlagEmoji,
  sortCityCandidates,
  sortCountryCandidates,
} from "./presentation";

describe("environmentStatusDescriptor (t079 AC-002)", () => {
  it("maps every known runtime state to the shared vocabulary", () => {
    expect(environmentStatusDescriptor("running")).toEqual({
      tone: "running",
      label: "statusRunning",
    });
    expect(environmentStatusDescriptor("starting").label).toBe(
      "statusStarting",
    );
    expect(environmentStatusDescriptor("stopping").label).toBe(
      "statusStopping",
    );
    expect(environmentStatusDescriptor("error")).toEqual({
      tone: "error",
      label: "statusError",
    });
    expect(environmentStatusDescriptor("stopped").label).toBe("statusStopped");
  });

  it("presents missing or out-of-enum states as an explicit unknown", () => {
    for (const value of [undefined, null, "", "half_open", "RUNNING"]) {
      expect(environmentStatusDescriptor(value).label).toBe("statusUnknown");
    }
  });
});

describe("proxyProbeErrorLabelKey (t079 AC-001)", () => {
  it("maps every known probe code to an accurate description key", () => {
    expect(proxyProbeErrorLabelKey("probe_failed")).toBe("proxyProbeFailed");
    expect(proxyProbeErrorLabelKey("probe_bad_response")).toBe(
      "proxyErrorProbeBadResponse",
    );
    expect(proxyProbeErrorLabelKey("supervisor_unavailable")).toBe(
      "proxyErrorSupervisorUnavailable",
    );
    expect(proxyProbeErrorLabelKey("proxy_credentials_unavailable")).toBe(
      "proxyErrorCredentialsUnavailable",
    );
    expect(proxyProbeErrorLabelKey("echo_unreachable")).toBe(
      "proxyErrorEchoUnreachable",
    );
    expect(proxyProbeErrorLabelKey("echo_proxy_unsupported")).toBe(
      "proxyErrorEchoProxyUnsupported",
    );
    expect(proxyProbeErrorLabelKey("invalid_echo_response")).toBe(
      "proxyErrorInvalidEchoResponse",
    );
    expect(proxyProbeErrorLabelKey("geoip_lookup_failed")).toBe(
      "proxyErrorGeoipLookupFailed",
    );
    expect(proxyProbeErrorLabelKey("proxy_auth_failed")).toBe(
      "proxyErrorAuthFailed",
    );
    expect(proxyProbeErrorLabelKey("proxy_unreachable")).toBe(
      "proxyErrorUnreachable",
    );
  });

  it("falls back to the generic failure label for unknown or missing codes", () => {
    expect(proxyProbeErrorLabelKey("some_future_code")).toBe(
      "proxyProbeFailed",
    );
    expect(proxyProbeErrorLabelKey(null)).toBe("proxyProbeFailed");
    expect(proxyProbeErrorLabelKey(undefined)).toBe("proxyProbeFailed");
    expect(proxyProbeErrorLabelKey("")).toBe("proxyProbeFailed");
  });
});

describe("region presentation (t079 AC-005)", () => {
  it("builds a flag only for known regions", () => {
    expect(regionFlagEmoji("US")).toBe("🇺🇸");
    expect(regionFlagEmoji("cn")).toBe("🇨🇳");
    expect(isRegionCode("US")).toBe(true);
    expect(isKnownRegion("US")).toBe(true);
    for (const bad of ["", "USA", "U1", "1S", null, undefined]) {
      expect(regionFlagEmoji(bad)).toBeNull();
      expect(isRegionCode(bad)).toBe(false);
      expect(isKnownRegion(bad)).toBe(false);
    }
  });

  it("never fabricates a flag for unassigned codes or unknown sentinels", () => {
    // Format-valid but not assigned in CLDR: GeoIP observations can
    // carry such codes, and AC-005 requires the placeholder branch.
    for (const unassigned of ["XX", "ZZ", "AA"]) {
      expect(isRegionCode(unassigned)).toBe(true);
      expect(isKnownRegion(unassigned)).toBe(false);
      expect(regionFlagEmoji(unassigned)).toBeNull();
      // The sort key falls back to the code itself, never to a
      // fabricated or "Unknown Region" name.
      expect(regionEnglishName(unassigned)).toBe(unassigned);
    }
  });

  it("resolves canonical English names for the sort key", () => {
    expect(regionEnglishName("US")).toBe("United States");
    expect(regionEnglishName("CN")).toBe("China");
  });
});

describe("candidate ordering (t079 AC-004)", () => {
  const ranges = [
    { country_code: "US", country_name: "美国", cities: ["New York"] },
    { country_code: "CN", country_name: "中国", cities: ["上海"] },
    { country_code: "JP", country_name: "日本", cities: ["Tokyo"] },
    { country_code: "CN", country_name: "中国", cities: ["北京"] },
    { country_code: "DE", country_name: "德国", cities: ["Berlin"] },
  ];

  it("sorts countries by canonical English name, deduped by code", () => {
    const sorted = sortCountryCandidates(ranges);
    expect(sorted.map((r) => r.country_code)).toEqual([
      "CN",
      "DE",
      "JP",
      "US",
    ]);
  });

  it("is independent of upstream order", () => {
    const shuffled = [...ranges].reverse();
    expect(
      sortCountryCandidates(shuffled).map((r) => r.country_code),
    ).toEqual(sortCountryCandidates(ranges).map((r) => r.country_code));
  });

  it("sorts and dedupes cities by the shared name rule", () => {
    expect(
      sortCityCandidates(["Zurich", "amsterdam", "Berlin", "amsterdam"]),
    ).toEqual(["amsterdam", "Berlin", "Zurich"]);
    const mixed = sortCityCandidates(["东京", "Osaka", "北京", "Kyoto"]);
    expect(mixed.indexOf("Kyoto")).toBeLessThan(mixed.indexOf("Osaka"));
    expect(new Set(mixed).size).toBe(4);
    expect(sortCityCandidates(mixed)).toEqual(mixed);
  });

  it("orders non-Latin names by the documented collator rule", () => {
    // The shared rule is Intl.Collator("en") (CLDR root order): Han
    // ideographs order by their CLDR radical/stroke sequence, which
    // pins 上海 < 东京 < 北京. If an ICU/CLDR upgrade changes that
    // order, this assertion — not a silent drift — must be revisited
    // together with the AC-004 rule statement.
    expect(sortCityCandidates(["北京", "东京", "上海"])).toEqual([
      "上海",
      "东京",
      "北京",
    ]);
    expect(compareNames("东京", "北京")).toBeLessThan(0);
  });

  it("compareNames is case-insensitive with a stable tie-break", () => {
    expect(compareNames("apple", "Banana")).toBeLessThan(0);
    expect(compareNames("a", "A")).not.toBe(0);
    expect(compareNames("same", "same")).toBe(0);
  });
});
