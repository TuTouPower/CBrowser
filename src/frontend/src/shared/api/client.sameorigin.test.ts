import { describe, it, expect, vi, afterEach } from "vitest";
import { ApiClient } from "./client";

/**
 * AC-001 (t025): every outbound entry point decides credentials/CSRF from
 * the FINAL resolved URL. Cross-origin targets — absolute, protocol
 * relative, backslash and mixed variants, or a cross-origin configured
 * base — must be rejected before fetch, and no cross-origin download URL
 * may be produced.
 */
function fetchSpyOk() {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
}

function calledUrls(spy: ReturnType<typeof fetchSpyOk>): string[] {
  return spy.mock.calls.map((call) => String(call[0]));
}

describe("ApiClient same-origin boundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  const crossOriginEndpoints = [
    "https://evil.example/api/v1/profiles",
    "http://evil.example/api/v1/profiles",
    "//evil.example/api/v1/profiles",
    "/\\evil.example/api/v1/profiles",
    "\\/evil.example/api/v1/profiles",
    "/\\/evil.example/api/v1/profiles",
    "\\\\evil.example\\api\\v1\\profiles",
    "https:evil.example/api/v1/profiles",
  ];
  for (const endpoint of crossOriginEndpoints) {
    it(`rejects cross-origin endpoint before fetch: ${endpoint}`, async () => {
      const spy = fetchSpyOk();
      const client = new ApiClient();
      await expect(client.request(endpoint)).rejects.toMatchObject({
        status: 0,
      });
      expect(spy).not.toHaveBeenCalled();
    });
  }

  it("never fetches a cross-origin target when configured with a cross-origin baseUrl", async () => {
    const spy = fetchSpyOk();
    const client = new ApiClient({
      baseUrl: "https://evil.example",
    } as never);
    await client.profiles.list().catch(() => undefined);
    const urls = calledUrls(spy);
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => !u.includes("evil.example"))).toBe(true);
    expect(
      urls.every((u) => new URL(u, window.location.origin).origin === window.location.origin),
    ).toBe(true);
  });

  it("allows relative and same-origin absolute endpoints with credentials", async () => {
    const spy = fetchSpyOk();
    const client = new ApiClient();
    await expect(client.profiles.list()).resolves.toEqual({ ok: true });
    await expect(
      client.request(`${window.location.origin}/api/v1/profiles`),
    ).resolves.toEqual({ ok: true });
    expect(spy).toHaveBeenCalledTimes(2);
    for (const call of spy.mock.calls) {
      expect(new URL(String(call[0]), window.location.origin).origin).toBe(
        window.location.origin,
      );
      expect(call[1]?.credentials).toBe("include");
    }
  });

  it("produces only same-origin download URLs even with a cross-origin configured base", () => {
    const hostile = new ApiClient({
      baseUrl: "https://evil.example",
    } as never);
    const url = hostile.artifacts.downloadUrl("p1", "a1");
    expect(url).not.toContain("evil.example");
    expect(new URL(url, window.location.origin).origin).toBe(
      window.location.origin,
    );
    expect(url.endsWith("/api/v1/profiles/p1/artifacts/a1")).toBe(true);
  });
});

describe("ApiClient logout failure handling (AC-002)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("clears the in-memory CSRF token when the logout request fails", async () => {
    document.cookie = "";
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (input) => {
        const url = String(input);
        if (url.includes("/api/v1/auth/login")) {
          return new Response(JSON.stringify({ csrf_token: "tok-1" }), {
            status: 200,
            headers: { "content-type": "application/json" },
          });
        }
        throw new TypeError("network down");
      });
    const client = new ApiClient();
    try {
      await client.auth.login({ password: "pw" });
      expect(client.getCsrfToken()).toBe("tok-1");
      await expect(client.auth.logout()).rejects.toThrow("network down");
      expect(client.getCsrfToken()).toBeNull();
    } finally {
      fetchSpy.mockRestore();
    }
  });
});
