import { describe, it, expect, vi, afterEach } from "vitest";
import { ProfileEventsClient } from "./sse";

/**
 * AC-001 (t025): the SSE entry point applies the same final-URL
 * same-origin rule as ApiClient. A cross-origin configured URL must never
 * be fetched (with credentials); the client connects only to the
 * same-origin events path.
 */
describe("ProfileEventsClient same-origin boundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("never fetches a cross-origin events URL", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "unauthorized" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new ProfileEventsClient({
      url: "https://evil.example/api/v1/events",
      reconnectIntervalMs: 10,
    } as never);
    client.start();
    await new Promise((resolve) => setTimeout(resolve, 60));
    client.stop();
    const urls = fetchSpy.mock.calls.map((call) => String(call[0]));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => !u.includes("evil.example"))).toBe(true);
    for (const u of urls) {
      expect(new URL(u, window.location.origin).origin).toBe(
        window.location.origin,
      );
      expect(new URL(u, window.location.origin).pathname).toBe(
        "/api/v1/events",
      );
    }
  });

  it("never fetches a backslash-variant cross-origin events URL", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "unauthorized" }), {
        status: 401,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new ProfileEventsClient({
      url: "/\\evil.example/api/v1/events",
      reconnectIntervalMs: 10,
    } as never);
    client.start();
    await new Promise((resolve) => setTimeout(resolve, 60));
    client.stop();
    const urls = fetchSpy.mock.calls.map((call) => String(call[0]));
    expect(urls.length).toBeGreaterThan(0);
    expect(urls.every((u) => !u.includes("evil.example"))).toBe(true);
  });
});
