/**
 * Frontend log channel (t058 A27).
 *
 * Render errors and other frontend faults are recorded here — an
 * in-memory ring buffer plus a `window` CustomEvent host and diagnostics
 * tooling can subscribe to — instead of being dropped or printed as a
 * console debug line. The buffer is bounded so a render loop cannot
 * grow it without limit; entries are plain data (no React internals).
 */

export type FrontendLogLevel = "error";

export interface FrontendLogEntry {
  level: FrontendLogLevel;
  message: string;
  stack?: string;
  componentStack?: string;
  source?: string;
  /** ISO timestamp of the record. */
  at: string;
}

export const FRONTEND_LOG_EVENT = "cbrowser:frontend-log";

const MAX_ENTRIES = 100;

const entries: FrontendLogEntry[] = [];

function toMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

function toStack(error: unknown): string | undefined {
  return error instanceof Error ? error.stack : undefined;
}

export const frontendLog = {
  logError(
    error: unknown,
    context: { source?: string; componentStack?: string | null } = {},
  ): FrontendLogEntry {
    const entry: FrontendLogEntry = {
      level: "error",
      message: toMessage(error),
      stack: toStack(error),
      componentStack: context.componentStack ?? undefined,
      source: context.source,
      at: new Date().toISOString(),
    };
    entries.push(entry);
    while (entries.length > MAX_ENTRIES) {
      entries.shift();
    }
    if (
      typeof window !== "undefined" &&
      typeof window.dispatchEvent === "function"
    ) {
      window.dispatchEvent(
        new CustomEvent(FRONTEND_LOG_EVENT, { detail: entry }),
      );
    }
    return entry;
  },

  getEntries(): FrontendLogEntry[] {
    return [...entries];
  },

  clear(): void {
    entries.length = 0;
  },
};
