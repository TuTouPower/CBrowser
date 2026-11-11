import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { AppProviders } from "./providers";
import { ApiClient } from "../shared/api/client";
import { ProfileEventsClient } from "../shared/api/sse";
import { useAuth } from "../features/auth/useAuth";

/**
 * AC-002 (t025): when the SSE stream reports unauthorized, the production
 * SseSyncBridge invokes logout. A failing logout request must still leave
 * the user logged out locally (auth state cleared, in-memory CSRF token
 * dropped, SSE stopped) and must not surface as an unhandled rejection.
 * Assertions are taken while the tree is still mounted, so they cannot be
 * satisfied by the bridge's unmount cleanup.
 */
function AuthProbe() {
  const { isAuthenticated } = useAuth();
  return <div data-testid="auth-state">{String(isAuthenticated)}</div>;
}

describe("AppProviders SSE unauthorized logout handling", () => {
  const fetchCalls: string[] = [];
  const unhandled: unknown[] = [];
  const onUnhandled = (event: PromiseRejectionEvent) => {
    unhandled.push(event.reason);
  };

  beforeEach(() => {
    fetchCalls.length = 0;
    unhandled.length = 0;
    document.cookie = "";
    window.addEventListener("unhandledrejection", onUnhandled);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const url = String(input);
      fetchCalls.push(url);
      if (url.includes("/api/v1/auth/session")) {
        return new Response(
          JSON.stringify({ authenticated: true, csrf_token: "tok-xyz" }),
          { status: 200, headers: { "content-type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/events")) {
        return new Response(JSON.stringify({ error: "unauthorized", message: "Not authenticated", retryable: false }), {
          status: 401,
          headers: { "content-type": "application/json" },
        });
      }
      if (url.includes("/api/v1/auth/logout")) {
        throw new TypeError("network down");
      }
      return new Response("{}", {
        status: 404,
        headers: { "content-type": "application/json" },
      });
    });
  });

  afterEach(() => {
    window.removeEventListener("unhandledrejection", onUnhandled);
    cleanup();
    vi.restoreAllMocks();
  });

  it("clears auth state and the CSRF token, stops SSE, and swallows the logout failure", async () => {
    const apiClient = new ApiClient();
    const sseClient = new ProfileEventsClient({ reconnectIntervalMs: 10 });
    const stopSpy = vi.spyOn(sseClient, "stop");

    render(
      <AppProviders apiClient={apiClient} sseClient={sseClient}>
        <AuthProbe />
      </AppProviders>,
    );

    // Session succeeds first (bridge mounts), then SSE 401 drives logout.
    await waitFor(() =>
      expect(screen.getByTestId("auth-state")).toHaveTextContent("true"),
    );
    await waitFor(() =>
      expect(screen.getByTestId("auth-state")).toHaveTextContent("false"),
    );
    expect(
      fetchCalls.some((u) => u.includes("/api/v1/auth/logout")),
    ).toBe(true);
    expect(stopSpy).toHaveBeenCalled();
    expect(apiClient.getCsrfToken()).toBeNull();

    // Give any stray rejection a chance to surface, then assert none did.
    await new Promise((resolve) => setTimeout(resolve, 150));
    expect(unhandled).toEqual([]);
    sseClient.stop();
  });
});
