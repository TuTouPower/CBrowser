import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
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
