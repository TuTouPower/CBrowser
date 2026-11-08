import { useEffect, useRef } from "react";
import type { NetworkApplyOperation } from "../../shared/api/types";

export const NETWORK_POLL_INTERVAL_MS = 1000;
export const NETWORK_POLL_DEADLINE_MS = 30_000;

export interface NetworkOperationPollHandlers {
  onCompleted: (operation: NetworkApplyOperation) => void;
  onFailed: (operation: NetworkApplyOperation) => void;
  onDeadline: (lastKnown: NetworkApplyOperation) => void;
}

export interface NetworkOperationPollOptions {
  intervalMs?: number;
  deadlineMs?: number;
}

export function isTerminalOperation(operation: NetworkApplyOperation): boolean {
  return operation.phase === "completed" || operation.phase === "failed";
}

export function useNetworkOperationPolling(
  getOperation: (
    operationId: string,
    signal: AbortSignal,
  ) => Promise<NetworkApplyOperation>,
  operation: NetworkApplyOperation | null,
  handlers: NetworkOperationPollHandlers,
  options: NetworkOperationPollOptions = {},
): void {
  const intervalMs = options.intervalMs ?? NETWORK_POLL_INTERVAL_MS;
  const deadlineMs = options.deadlineMs ?? NETWORK_POLL_DEADLINE_MS;
  const operationId = operation?.operation_id ?? null;
  const operationRef = useRef(operation);
  const getOperationRef = useRef(getOperation);
  const handlersRef = useRef(handlers);
  operationRef.current = operation;
  getOperationRef.current = getOperation;
  handlersRef.current = handlers;

  useEffect(() => {
    const seed = operationRef.current;
    if (
      !operationId ||
      !seed ||
      seed.operation_id !== operationId ||
      isTerminalOperation(seed)
    ) {
      return;
    }
    const id = operationId;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;
    const startedAt = Date.now();
    let lastKnown: NetworkApplyOperation = seed;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const stop = () => {
      cancelled = true;
      clearTimer();
      if (controller) {
        controller.abort();
        controller = null;
      }
    };

    const reachedDeadline = () => Date.now() - startedAt >= deadlineMs;

    const fireDeadline = () => {
      stop();
      handlersRef.current.onDeadline(lastKnown);
    };

    const schedule = () => {
      if (cancelled) return;
      clearTimer();
      timer = setTimeout(runTick, intervalMs);
    };

    const scheduleOrDeadline = () => {
      if (reachedDeadline()) {
        fireDeadline();
        return;
      }
      schedule();
    };

    async function runTick(): Promise<void> {
      if (cancelled) return;
      if (reachedDeadline()) {
        fireDeadline();
        return;
      }
      controller = new AbortController();
      const signal = controller.signal;
      try {
        const current = await getOperationRef.current(id, signal);
        if (cancelled) return;
        lastKnown = current;
        if (current.phase === "completed") {
          stop();
          handlersRef.current.onCompleted(current);
          return;
        }
        if (current.phase === "failed") {
          stop();
          handlersRef.current.onFailed(current);
          return;
        }
        scheduleOrDeadline();
      } catch {
        if (cancelled) return;
        scheduleOrDeadline();
      } finally {
        if (controller && controller.signal === signal) {
          controller = null;
        }
      }
    }

    schedule();
    return stop;
  }, [operationId, intervalMs, deadlineMs]);
}
