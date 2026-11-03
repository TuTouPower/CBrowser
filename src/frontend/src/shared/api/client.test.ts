import { describe, it, expect, beforeAll, afterAll, beforeEach, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import { ApiClient, ApiError } from "./client";

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

  it("sends credentials: 'include' on GET requests", async () => {
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

  it("reads cbrowser_csrf cookie and sends X-CSRF-Token header on write requests", async () => {
    const client = new ApiClient({ baseUrl: serverUrl });
    document.cookie = "cbrowser_csrf=csrf_secret_token_12345; path=/";

    mockHandler = (_req, res) => {
      res.writeHead(201, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ id: "p2", name: "New Profile" }));
    };

    const newProfile = await client.profiles.create({ name: "New Profile" });
    expect(newProfile.name).toBe("New Profile");
    expect(lastRequest?.method).toBe("POST");
    expect(lastRequest?.headers["x-csrf-token"]).toBe("csrf_secret_token_12345");
    expect(JSON.parse(lastRequest?.body || "{}")).toEqual({ name: "New Profile" });
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

    await expect(client.profiles.create({ name: "" })).rejects.toThrow("Invalid profile name");
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

describe("ApiClient idempotency", () => {
  it("uses the caller-supplied action key for retries", async () => {
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
      await client.profiles.create({ name: "same" }, "action-key-1");
      await client.profiles.create({ name: "same" }, "action-key-1");
      expect(keys).toEqual(["action-key-1", "action-key-1"]);
    } finally {
      fetchSpy.mockRestore();
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
    expect(requestSpy.mock.calls[0][2]).toBe(22);
    expect(requestSpy.mock.calls[1][2]).toBe(33);
  });
});
