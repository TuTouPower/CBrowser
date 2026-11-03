import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { ApiClient, ApiError, shouldRetryRequest } from "./client";
import { DEFAULT_PROFILE_CREATE_VALUES } from "./types";

describe("ApiClient", () => {
  let server: http.Server;
  let serverUrl: string;
  let lastRequest: {
    method?: string;
    url?: string;
    headers: http.IncomingHttpHeaders;
    body?: string;
  } | null = null;
  let mockHandler: ((req: http.IncomingMessage, res: http.ServerResponse) => void) | null = null;

  beforeAll(async () => {
    server = http.createServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk;
      });
      req.on("end", () => {
        lastRequest = {
          method: req.method,
          url: req.url,
          headers: req.headers,
          body,
        };
        if (mockHandler) {
          mockHandler(req, res);
        } else {
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ status: "ok" }));
        }
      });
    });

    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });

    const addr = server.address() as AddressInfo;
    serverUrl = `http://127.0.0.1:${addr.port}`;
  });

  afterAll(async () => {
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  });

  beforeEach(() => {
    lastRequest = null;
    mockHandler = null;
    document.cookie = "";
  });

  it("lists profiles with a GET to the profiles endpoint", async () => {
    const client = new ApiClient({ baseUrl: serverUrl });
    mockHandler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify([{ id: "p1", name: "Profile 1" }]));
    };

    const profiles = await client.profiles.list();
    expect(profiles).toEqual([{ id: "p1", name: "Profile 1" }]);
    expect(lastRequest?.method).toBe("GET");
    expect(lastRequest?.url).toBe("/api/v1/profiles");
  });

  it("passes credentials: 'include' to fetch", async () => {
    // The credentials mode is a fetch-init property; it cannot be observed
    // at the HTTP server, so assert it on the fetch call itself.
    const seen: RequestInit[] = [];
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (_url, init) => {
        seen.push(init ?? {});
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      });
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:1" });
    try {
      await client.profiles.list();
      expect(seen).toHaveLength(1);
      expect(seen[0]?.credentials).toBe("include");
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("reads cbrowser_csrf cookie and sends X-CSRF-Token header on write requests", async () => {
    const client = new ApiClient({ baseUrl: serverUrl });
    document.cookie = "cbrowser_csrf=csrf_secret_token_12345; path=/";

    mockHandler = (_req, res) => {
      res.writeHead(201, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ id: "p2", name: "New Profile" }));
    };

    const newProfile = await client.profiles.create({
      ...DEFAULT_PROFILE_CREATE_VALUES,
      name: "New Profile",
    });
    expect(newProfile.name).toBe("New Profile");
    expect(lastRequest?.method).toBe("POST");
    expect(lastRequest?.headers["x-csrf-token"]).toBe("csrf_secret_token_12345");
    expect(JSON.parse(lastRequest?.body || "{}")).toEqual({
      ...DEFAULT_PROFILE_CREATE_VALUES,
      name: "New Profile",
    });
  });

  it("sends X-CSRF-Token on writes including desired-state PATCH", async () => {
    const client = new ApiClient({ baseUrl: serverUrl });
    document.cookie = "cbrowser_csrf=token_for_update; path=/";

    mockHandler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ id: "p1", name: "Updated" }));
    };
    await client.profiles.update("p1", { name: "Updated" });
    expect(lastRequest?.method).toBe("PATCH");
    expect(lastRequest?.headers["x-csrf-token"]).toBe("token_for_update");

    mockHandler = (_req, res) => {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ profile_id: "p1", desired_state: "running", observed_state: "running" }));
    };
    await client.profiles.setDesiredState("p1", "running");
    expect(lastRequest?.method).toBe("PATCH");
    expect(lastRequest?.headers["x-csrf-token"]).toBe("token_for_update");

    mockHandler = (_req, res) => {
      res.writeHead(204);
      res.end();
    };
    await client.profiles.delete("p1");
    expect(lastRequest?.method).toBe("DELETE");
    expect(lastRequest?.headers["x-csrf-token"]).toBe("token_for_update");
  });

  it("triggers onUnauthorized callback on 401 status", async () => {
    let unauthorizedTriggered = false;
    const client = new ApiClient({
      baseUrl: serverUrl,
      onUnauthorized: () => {
        unauthorizedTriggered = true;
      },
    });

    mockHandler = (_req, res) => {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "Not authenticated" }));
    };

    await expect(client.profiles.list()).rejects.toThrow(ApiError);
    expect(unauthorizedTriggered).toBe(true);
  });

  it("surfaces server error detail from JSON response", async () => {
    const client = new ApiClient({ baseUrl: serverUrl });
    mockHandler = (_req, res) => {
      res.writeHead(400, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ detail: "Invalid profile name" }));
    };

    await expect(
      client.profiles.create({ ...DEFAULT_PROFILE_CREATE_VALUES, name: "" }),
    ).rejects.toThrow("Invalid profile name");
  });
});

describe("ApiClient hardening", () => {
  it("rejects cross-origin absolute URLs before sending credentials", async () => {
    const client = new ApiClient();
    await expect(client.request("https://evil.example/api")).rejects.toMatchObject({
      status: 0,
    });
  });

  it("maps timeout to a retryable ApiError", async () => {
    const server = http.createServer((_req, res) => {
      setTimeout(() => res.end("{}"), 200);
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const address = server.address() as import("node:net").AddressInfo;
    const client = new ApiClient({
      baseUrl: `http://127.0.0.1:${address.port}`,
      defaultTimeoutMs: 10,
    });
    try {
      await expect(client.request("/slow")).rejects.toMatchObject({
        errorCode: "timeout",
        retryable: true,
      });
    } finally {
      server.close();
    }
  });

  it("carries error code, retryable flag and detail", async () => {
    document.cookie = "";
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:1" });
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: "validation_error",
          retryable: false,
          detail: [{ loc: ["body", "launch_args"], msg: "not allowed" }],
        }),
        { status: 422, headers: { "content-type": "application/json" } },
      ),
    );
    try {
      await expect(client.profiles.list()).rejects.toMatchObject({
        errorCode: "validation_error",
        retryable: false,
        status: 422,
        detail: [{ loc: ["body", "launch_args"], msg: "not allowed" }],
      });
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("does not treat a 503 without retryable payload as retryable", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "database_busy" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:1" });
    try {
      await expect(client.profiles.list()).rejects.toMatchObject({
        retryable: false,
      });
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("exposes separate upload and long-operation timeout policies", () => {
    const client = new ApiClient({
      defaultTimeoutMs: 11,
      uploadTimeoutMs: 22,
      longOperationTimeoutMs: 33,
    });
    expect([
      client.defaultTimeoutMs,
      client.uploadTimeoutMs,
      client.longOperationTimeoutMs,
    ]).toEqual([11, 22, 33]);
  });

  it("does not call fetch for protocol-relative cross-origin URLs", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const client = new ApiClient();
    await expect(client.request("//evil.example/api")).rejects.toMatchObject({
      status: 0,
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

describe("ApiClient artifacts", () => {
  it("builds the artifact download URL from the configured base URL", () => {
    const client = new ApiClient({ baseUrl: "http://host:8080" });
    expect(client.artifacts.downloadUrl("p 1", "a/1")).toBe(
      "http://host:8080/api/v1/profiles/p%201/artifacts/a%2F1",
    );
    const defaultClient = new ApiClient();
    expect(defaultClient.artifacts.downloadUrl("p1", "a1")).toBe(
      "/api/v1/profiles/p1/artifacts/a1",
    );
  });
});

describe("ApiClient idempotency", () => {
  it("sends the caller-supplied action key as the Idempotency-Key header", async () => {
    // Header pass-through only: the evidence that one key survives React
    // Query retries lives in useProfilesQuery.retry.test.tsx (A22).
    const keys: string[] = [];
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) => {
      keys.push(new Headers(init?.headers).get("Idempotency-Key") || "");
      return new Response(JSON.stringify({ id: "p1" }), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    });
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:1" });
    try {
      await client.profiles.create(
        { ...DEFAULT_PROFILE_CREATE_VALUES, name: "same" },
        "action-key-1",
      );
      await client.profiles.create(
        { ...DEFAULT_PROFILE_CREATE_VALUES, name: "same" },
        "action-key-1",
      );
      expect(keys).toEqual(["action-key-1", "action-key-1"]);
    } finally {
      fetchSpy.mockRestore();
    }
  });
});

describe("ApiClient cancellation", () => {
  function abortingFetch() {
    return vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((_url, init) => {
        return new Promise<Response>((_resolve, reject) => {
          const signal = init?.signal;
          if (!signal) {
            reject(new Error("fetch called without a signal"));
            return;
          }
          if (signal.aborted) {
            reject(new DOMException("Aborted", "AbortError"));
            return;
          }
          signal.addEventListener(
            "abort",
            () => reject(new DOMException("Aborted", "AbortError")),
            { once: true },
          );
        });
      });
  }

  it("distinguishes external cancellation from timeout: cancelled is not retryable", async () => {
    const fetchSpy = abortingFetch();
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:1",
      defaultTimeoutMs: 60_000,
    });
    const external = new AbortController();
    const removeSpy = vi.spyOn(external.signal, "removeEventListener");
    try {
      const pending = client.request("/api/v1/profiles", {
        signal: external.signal,
      });
      const assertion = expect(pending).rejects.toMatchObject({
        name: "ApiError",
        errorCode: "cancelled",
        retryable: false,
      });
      external.abort();
      await assertion;
      const err = await pending.catch((e: unknown) => e);
      expect(shouldRetryRequest(0, err)).toBe(false);
      expect(shouldRetryRequest(1, err)).toBe(false);
      // The abort listener is released on the cancellation path too, not
      // only after a successful settle (A18).
      expect(removeSpy).toHaveBeenCalledWith("abort", expect.any(Function));
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("times out with a retryable error and still removes the external listener", async () => {
    const fetchSpy = abortingFetch();
    const external = new AbortController();
    const removeSpy = vi.spyOn(external.signal, "removeEventListener");
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:1",
      defaultTimeoutMs: 30,
    });
    try {
      const pending = client.request("/api/v1/profiles", {
        signal: external.signal,
      });
      await expect(pending).rejects.toMatchObject({
        name: "ApiError",
        errorCode: "timeout",
        retryable: true,
      });
      expect(removeSpy).toHaveBeenCalledWith("abort", expect.any(Function));
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("cancels while the response body is still streaming (A18)", async () => {
    // The response head arrives immediately but the body never completes;
    // the external abort listener and the timeout must stay armed until
    // the body has been read, not just until fetch resolves.
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((_url, init) => {
        const stream = new ReadableStream<Uint8Array>({
          start(controller) {
            init?.signal?.addEventListener("abort", () => {
              controller.error(new DOMException("Aborted", "AbortError"));
            });
          },
        });
        return Promise.resolve(
          new Response(stream, {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
        );
      });
    const external = new AbortController();
    const removeSpy = vi.spyOn(external.signal, "removeEventListener");
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:1",
      defaultTimeoutMs: 60_000,
    });
    try {
      const pending = client.request("/api/v1/profiles", {
        signal: external.signal,
      });
      const assertion = expect(pending).rejects.toMatchObject({
        name: "ApiError",
        errorCode: "cancelled",
        retryable: false,
      });
      // Let fetch resolve and body reading begin before cancelling.
      await new Promise((resolve) => setTimeout(resolve, 0));
      external.abort();
      await assertion;
      expect(removeSpy).toHaveBeenCalledWith("abort", expect.any(Function));
    } finally {
      fetchSpy.mockRestore();
    }
  });

  it("removes the external abort listener once the request settles", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const external = new AbortController();
    const removeSpy = vi.spyOn(external.signal, "removeEventListener");
    const client = new ApiClient({ baseUrl: "http://127.0.0.1:1" });
    try {
      await client.request("/api/v1/profiles", { signal: external.signal });
      expect(removeSpy).toHaveBeenCalledWith(
        "abort",
        expect.any(Function),
      );
    } finally {
      fetchSpy.mockRestore();
      removeSpy.mockRestore();
    }
  });
});

describe("timeout policy wiring", () => {
  it("uses upload and long-operation timeouts", async () => {
    const client = new ApiClient({
      baseUrl: "http://127.0.0.1:1",
      uploadTimeoutMs: 22,
      longOperationTimeoutMs: 33,
    });
    const requestSpy = vi
      .spyOn(client, "request")
      .mockResolvedValue({} as never);
    const file = new File(["x"], "x.txt", { type: "text/plain" });
    await client.artifacts.upload("p1", file, "key");
    await client.profiles.stop("p1", "key");
    expect(requestSpy.mock.calls[0]?.[2]).toBe(22);
    expect(requestSpy.mock.calls[1]?.[2]).toBe(33);
  });
});
