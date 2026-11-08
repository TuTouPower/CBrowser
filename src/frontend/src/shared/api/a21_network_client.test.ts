import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";

function fetchOk(body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
    new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "";
});

describe("A21 ApiClient network domain methods use the unified request path", () => {
  it("updateSettings sends a same-origin PUT with CSRF and credentials", async () => {
    const spy = fetchOk({ status: "ok" });
    const client = new ApiClient();
    client.setCsrfToken("csrf-tok");

    const result = await client.network.updateSettings({
      lan_access_enabled: true,
      lan_advertised_ip: "192.168.31.76",
      https_port: 58888,
    });

    expect(result.status).toBe("ok");
    expect(spy).toHaveBeenCalledTimes(1);
    const [url, init] = spy.mock.calls[0]!;
    expect(new URL(String(url), window.location.origin).pathname).toBe(
      "/api/v1/network/settings",
    );
    expect(init?.method).toBe("PUT");
    expect(init?.credentials).toBe("include");
    expect((init?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-tok");
    expect(init?.body).toBe(
      JSON.stringify({
        lan_access_enabled: true,
        lan_advertised_ip: "192.168.31.76",
        https_port: 58888,
      }),
    );
  });

  it("apply sends a same-origin POST with CSRF, credentials and request body", async () => {
    const spy = fetchOk({
      operation_id: "op-1",
      target_version: 2,
      phase: "pending",
      created_at: "2026-11-08T00:00:00+08:00",
      updated_at: "2026-11-08T00:00:00+08:00",
    });
    const client = new ApiClient();
    client.setCsrfToken("csrf-tok");

    const result = await client.network.apply({ admin_password: "pw" });

    expect(result.operation_id).toBe("op-1");
    const [url, init] = spy.mock.calls[0]!;
    expect(new URL(String(url), window.location.origin).pathname).toBe(
      "/api/v1/network/apply",
    );
    expect(init?.method).toBe("POST");
    expect(init?.credentials).toBe("include");
    expect((init?.headers as Headers).get("X-CSRF-Token")).toBe("csrf-tok");
    expect(init?.body).toBe(JSON.stringify({ admin_password: "pw" }));
  });

  it("getSettings and checkDisconnect use the same-origin GET path", async () => {
    const spy = fetchOk({ pending_config: {}, applied_version: {} });
    const client = new ApiClient();

    await client.network.getSettings();
    await client.network.checkDisconnect();

    expect(spy).toHaveBeenCalledTimes(2);
    for (const call of spy.mock.calls) {
      expect(new URL(String(call[0]), window.location.origin).origin).toBe(
        window.location.origin,
      );
      expect(call[1]?.credentials).toBe("include");
    }
    expect(
      new URL(String(spy.mock.calls[0]![0]), window.location.origin).pathname,
    ).toBe("/api/v1/network/settings");
    expect(
      new URL(String(spy.mock.calls[1]![0]), window.location.origin).pathname,
    ).toBe("/api/v1/network/check-disconnect");
  });

  it("getOperation forwards the caller abort signal through the request layer", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    const client = new ApiClient();
    const controller = new AbortController();

    const promise = client.network.getOperation("op-1", controller.signal);
    controller.abort();
    await expect(promise).rejects.toMatchObject({ errorCode: "cancelled" });
  });
});
