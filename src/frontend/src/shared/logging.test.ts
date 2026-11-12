import { afterEach, describe, expect, it, vi } from "vitest";
import {
  FRONTEND_LOG_EVENT,
  frontendLog,
} from "./logging";

// t058 A27: the frontend log channel ErrorBoundary reports to. It is an
// in-memory ring plus a window event — observable in tests and by host
// diagnostics tooling — and never a console debug print.
describe("frontendLog", () => {
  afterEach(() => {
    frontendLog.clear();
    vi.restoreAllMocks();
  });

  it("records an error with message, stack, source and timestamp", () => {
    const error = new Error("boom");
    const entry = frontendLog.logError(error, { source: "ErrorBoundary" });

    expect(entry.level).toBe("error");
    expect(entry.message).toBe("boom");
    expect(entry.stack).toContain("Error");
    expect(entry.source).toBe("ErrorBoundary");
    expect(entry.at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(frontendLog.getEntries()).toEqual([entry]);
  });

  it("records a component stack when React provides one", () => {
    const entry = frontendLog.logError(new Error("boom"), {
      source: "ErrorBoundary",
      componentStack: "\n    at Bomb",
    });
    expect(entry.componentStack).toContain("at Bomb");
  });

  it("dispatches a window event carrying the entry", () => {
    const listener = vi.fn();
    window.addEventListener(FRONTEND_LOG_EVENT, listener);
    try {
      const entry = frontendLog.logError(new Error("boom"));
      expect(listener).toHaveBeenCalledTimes(1);
      const event = listener.mock.calls[0]![0] as CustomEvent;
      expect(event.detail).toBe(entry);
    } finally {
      window.removeEventListener(FRONTEND_LOG_EVENT, listener);
    }
  });

  it("keeps only the newest 100 entries", () => {
    for (let i = 0; i < 105; i++) {
      frontendLog.logError(new Error(`error ${i}`));
    }
    const entries = frontendLog.getEntries();
    expect(entries).toHaveLength(100);
    expect(entries[0]!.message).toBe("error 5");
    expect(entries[99]!.message).toBe("error 104");
  });

  it("never writes to the console", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
    frontendLog.logError(new Error("boom"));
    expect(errorSpy).not.toHaveBeenCalled();
    expect(logSpy).not.toHaveBeenCalled();
  });
});
