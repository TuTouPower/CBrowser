import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import {
  QueryClient,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { AppProviders } from "./providers";
import { ApiError, type ApiClient } from "../shared/api/client";
import type { ProfileEventsClient } from "../shared/api/sse";

/**
 * AC-005 (t025): the production AppProviders default QueryClient (no
 * injected client) must wire shouldRetryRequest for both queries and
 * mutations: retryable errors retry a bounded number of times, caller
 * cancellations and non-retryable errors never retry.
 */
function makeStubApi(): ApiClient {
  return {
    setOnUnauthorized: vi.fn(),
    setCsrfToken: vi.fn(),
    auth: {
      session: vi.fn(async () => {
        throw new ApiError("Authentication required", 401);
      }),
      login: vi.fn(),
      logout: vi.fn(),
    },
    health: { check: vi.fn(async () => undefined) },
    profiles: { list: vi.fn(async () => []) },
  } as unknown as ApiClient;
}

function makeFakeSse(): ProfileEventsClient {
  return {
    start: vi.fn(),
    stop: vi.fn(),
    onEvent: vi.fn(() => () => {}),
    onError: vi.fn(() => () => {}),
    setOnUnauthorized: vi.fn(),
  } as unknown as ProfileEventsClient;
}

let capturedClient: QueryClient | null = null;
function ClientProbe() {
  capturedClient = useQueryClient();
  return null;
}

type RetryFn = (failureCount: number, error: unknown) => boolean;

describe("AppProviders default QueryClient retry wiring", () => {
  beforeEach(() => {
    capturedClient = null;
    localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("wires bounded retry for queries and mutations, never for cancellations", () => {
    render(
      <AppProviders apiClient={makeStubApi()} sseClient={makeFakeSse()}>
        <ClientProbe />
      </AppProviders>,
    );
    const defaults = capturedClient?.getDefaultOptions();
    const queryRetry = defaults?.queries?.retry as RetryFn;
    const mutationRetry = defaults?.mutations?.retry as RetryFn;
    expect(typeof queryRetry).toBe("function");
    expect(typeof mutationRetry).toBe("function");

    const retryable = new ApiError(
      "busy",
      503,
      undefined,
      "database_busy",
      true,
    );
    const cancelled = new ApiError(
      "Request cancelled",
      0,
      undefined,
      "cancelled",
      false,
    );
    const plain = new Error("boom");
    for (const retry of [queryRetry, mutationRetry]) {
      expect(retry(0, retryable)).toBe(true);
      expect(retry(1, retryable)).toBe(true);
      expect(retry(2, retryable)).toBe(false);
      expect(retry(0, cancelled)).toBe(false);
      expect(retry(1, cancelled)).toBe(false);
      expect(retry(0, plain)).toBe(true);
      expect(retry(1, plain)).toBe(false);
    }
  });

  it("actually retries a query that fails once with a retryable error", async () => {
    let attempts = 0;
    function QueryProbe() {
      const { data } = useQuery({
        queryKey: ["ac005-probe"],
        queryFn: async () => {
          attempts += 1;
          if (attempts === 1) {
            throw new ApiError("busy", 503, undefined, "database_busy", true);
          }
          return "recovered";
        },
      });
      return <div data-testid="probe-data">{data ?? "pending"}</div>;
    }
    render(
      <AppProviders apiClient={makeStubApi()} sseClient={makeFakeSse()}>
        <QueryProbe />
      </AppProviders>,
    );
    expect(
      await screen.findByText("recovered", undefined, { timeout: 5000 }),
    ).toBeTruthy();
    expect(attempts).toBe(2);
  });
});
