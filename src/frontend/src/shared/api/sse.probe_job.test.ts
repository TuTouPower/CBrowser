/** t094: probe_job_progress frames travel through the existing SSE channel
 * with id/event/data, reach onProbeJobProgress only, and are validated against
 * the generated ProxyProbeJob read model. */

import { describe, it, expect, beforeAll, afterAll, vi } from "vitest";
import http from "node:http";
import type { AddressInfo } from "node:net";
import {
  ProfileEventsClient,
  parseProbeJobProgressEvent,
  type ProbeJobProgressEvent,
} from "./sse";

const runningJob = {
  job_id: "job-1",
  state: "running",
  total: 2,
  completed: 1,
  failed: 0,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:01Z",
  members: [
    { proxy_id: "px1", state: "ok", observed_at: "2026-01-01T00:00:01Z" },
    { proxy_id: "px2", state: "pending" },
  ],
};

describe("ProfileEventsClient probe_job_progress", () => {
  let server: http.Server;
  let currentRes: http.ServerResponse | null = null;

  beforeAll(async () => {
    server = http.createServer((_req, res) => {
      currentRes = res;
      res.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      });
      res.write(
        `id: probe-1\nevent: probe_job_progress\ndata: ${JSON.stringify(runningJob)}\n\n`,
      );
      res.write(
        `event: probe_job_progress\ndata: ${JSON.stringify({ job_id: "x", state: "running" })}\n\n`,
      );
      res.write(
        `data: ${JSON.stringify({
          profile_id: "p1",
          display_number: 1,
          desired_state: "running",
          observed_state: "running",
          failure_count: 0,
          restart_blocked: false,
          updated_at: "2026-01-01T00:00:00Z",
        })}\n\n`,
      );
    });

    await new Promise<void>((resolve) => {
      server.listen(0, "127.0.0.1", () => resolve());
    });

    const addr = server.address() as AddressInfo;
    const serverUrl = `http://127.0.0.1:${addr.port}/api/v1/events`;
    const realFetch = globalThis.fetch;
    vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), serverUrl);
      return realFetch(
        `http://127.0.0.1:${addr.port}${url.pathname}${url.search}`,
        init,
      );
    });
  });

  afterAll(async () => {
    vi.unstubAllGlobals();
    if (currentRes && !currentRes.destroyed) currentRes.destroy();
    await new Promise<void>((resolve) => {
      server.close(() => resolve());
    });
  });

  it("delivers valid progress to onProbeJobProgress and routes malformed payloads to onError", async () => {
    const progress: ProbeJobProgressEvent[] = [];
    const runtime: unknown[] = [];
    const errors: unknown[] = [];
    const client = new ProfileEventsClient();
    client.onProbeJobProgress((event) => progress.push(event));
    client.onEvent((event) => runtime.push(event));
    client.onError((error) => errors.push(error));
    client.start();
    try {
      await vi.waitFor(() => {
        expect(progress).toHaveLength(1);
        expect(runtime).toHaveLength(1);
        expect(errors.length).toBeGreaterThanOrEqual(1);
      });
    } finally {
      client.stop();
    }
    expect(progress[0]).toEqual({
      ...runningJob,
      event: "probe_job_progress",
    });
  });

  it("replays the last progress event id via Last-Event-ID", async () => {
    const client = new ProfileEventsClient();
    client.start();
    try {
      await vi.waitFor(() =>
        expect(client.getLastEventId()).toBe("probe-1"),
      );
    } finally {
      client.stop();
    }
  });
});

describe("parseProbeJobProgressEvent", () => {
  it("accepts a complete job snapshot and attaches the event discriminator", () => {
    expect(parseProbeJobProgressEvent(runningJob)).toEqual({
      ...runningJob,
      event: "probe_job_progress",
    });
  });

  it("rejects wrong state, missing counters, bad members and non-objects", () => {
    expect(parseProbeJobProgressEvent(null)).toBeNull();
    expect(parseProbeJobProgressEvent([])).toBeNull();
    expect(
      parseProbeJobProgressEvent({ ...runningJob, state: "queued" }),
    ).toBeNull();
    expect(parseProbeJobProgressEvent({ ...runningJob, total: "2" })).toBeNull();
    expect(
      parseProbeJobProgressEvent({
        ...runningJob,
        members: [{ proxy_id: "px1", state: "unknown" }],
      }),
    ).toBeNull();
  });
});
