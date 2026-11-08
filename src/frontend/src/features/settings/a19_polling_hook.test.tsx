import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  NETWORK_POLL_INTERVAL_MS,
  useNetworkOperationPolling,
} from "./useNetworkOperationPolling";
import type { NetworkApplyOperation } from "../../shared/api/types";

function operation(
  overrides: Partial<NetworkApplyOperation> = {},
): NetworkApplyOperation {
  return {
    operation_id: "op-1",
    target_version: 2,
    phase: "rebuilding_caddy",
    created_at: "2026-11-08T00:00:00+08:00",
    updated_at: "2026-11-08T00:00:00+08:00",
    ...overrides,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function handlers() {
  return {
    onCompleted: vi.fn(),
    onFailed: vi.fn(),
    onDeadline: vi.fn(),
  };
}

describe("A19 useNetworkOperationPolling generation fence", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("switches operations: the old generation sends no new request and its late response is discarded", async () => {
    const first = deferred<NetworkApplyOperation>();
    const getOperation = vi.fn(async (id: string) => {
      if (id === "op-1") return first.promise;
      return operation({ operation_id: id, phase: "completed" });
    });
    const callbacks = handlers();
    const view = renderHook(
      ({ current }) =>
        useNetworkOperationPolling(getOperation, current, callbacks),
      { initialProps: { current: operation({ operation_id: "op-1" }) } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(NETWORK_POLL_INTERVAL_MS);
    });
    expect(getOperation).toHaveBeenCalledTimes(1);

    view.rerender({ current: operation({ operation_id: "op-2" }) });
    first.resolve(operation({ operation_id: "op-1", phase: "completed" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(callbacks.onCompleted).not.toHaveBeenCalled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(NETWORK_POLL_INTERVAL_MS);
    });
    expect(callbacks.onCompleted).toHaveBeenCalledTimes(1);
    expect(
      getOperation.mock.calls.filter((call) => call[0] === "op-1"),
    ).toHaveLength(1);
    view.unmount();
  });

  it("aborts the in-flight request signal on unmount", async () => {
    const signals: AbortSignal[] = [];
    const getOperation = vi.fn(
      async (_id: string, signal: AbortSignal) => {
        signals.push(signal);
        return new Promise<NetworkApplyOperation>(() => {});
      },
    );
    const view = renderHook(() =>
      useNetworkOperationPolling(getOperation, operation(), handlers()),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(NETWORK_POLL_INTERVAL_MS);
    });
    expect(signals).toHaveLength(1);
    expect(signals[0]?.aborted).toBe(false);

    view.unmount();
    expect(signals[0]?.aborted).toBe(true);
  });

  it("stops after a bounded deadline of sustained disconnects", async () => {
    const getOperation = vi.fn(async () => {
      throw new Error("connection lost");
    });
    const callbacks = handlers();
    renderHook(() =>
      useNetworkOperationPolling(getOperation, operation(), callbacks, {
        intervalMs: 100,
        deadlineMs: 500,
      }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(callbacks.onDeadline).toHaveBeenCalledTimes(1);
    expect(getOperation).toHaveBeenCalledTimes(4);
  });

  it("fires the deadline by real elapsed time under slow requests, not by counting intervals", async () => {
    const slowMs = 10_000;
    const fired: { at: number | null } = { at: null };
    const getOperation = vi.fn(
      (_id: string, _signal: AbortSignal) =>
        new Promise<NetworkApplyOperation>((resolve) => {
          setTimeout(
            () => resolve(operation({ phase: "rebuilding_caddy" })),
            slowMs,
          );
        }),
    );
    const callbacks = handlers();
    callbacks.onDeadline.mockImplementation(() => {
      fired.at = Date.now();
    });
    const startedAt = Date.now();
    renderHook(() =>
      useNetworkOperationPolling(getOperation, operation(), callbacks, {
        intervalMs: 1000,
        deadlineMs: 30_000,
      }),
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });

    expect(callbacks.onDeadline).toHaveBeenCalledTimes(1);
    expect(fired.at).not.toBeNull();
    expect((fired.at as number) - startedAt).toBeGreaterThanOrEqual(30_000);
    expect((fired.at as number) - startedAt).toBeLessThan(60_000);
    expect(getOperation).toHaveBeenCalledTimes(3);
  });
});
