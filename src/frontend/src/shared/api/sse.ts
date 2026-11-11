import type { ProfileRuntimeStatusEvent } from "./types";
import { resolveSameOriginUrl } from "./same_origin";

/**
 * The wire shape of `runtime_state` events is owned by the generated
 * OpenAPI type; this alias keeps existing imports stable.
 */
export type ProfileRuntimeEvent = ProfileRuntimeStatusEvent;

export interface ProfilePreviewEvent {
  event: "profile_preview";
  profile_id: string;
  captured_at: string;
}

/** t056 A31: a group/proxy write on any client.  The payload carries only
 * the changed entity id (null for a reorder); receivers invalidate their
 * group/proxy/profile lists and refetch — the event itself is not data. */
export interface ReferenceChangedEvent {
  event: "groups_changed" | "proxies_changed";
  entity_id: string | null;
}

export type ProfileSseEvent =
  | ProfileRuntimeEvent
  | ProfilePreviewEvent
  | ReferenceChangedEvent;

export type ProfileEventListener = (event: ProfileRuntimeEvent) => void;
export type ProfilePreviewEventListener = (event: ProfilePreviewEvent) => void;
export type ReferenceChangedEventListener = (
  event: ReferenceChangedEvent,
) => void;
export type ProfileErrorListener = (error: unknown) => void;

export function isProfilePreviewEvent(
  event: ProfileSseEvent,
): event is ProfilePreviewEvent {
  return "event" in event && event.event === "profile_preview";
}

export function isReferenceChangedEvent(
  event: ProfileSseEvent,
): event is ReferenceChangedEvent {
  return (
    "event" in event &&
    (event.event === "groups_changed" || event.event === "proxies_changed")
  );
}

const DESIRED_STATES = new Set(["stopped", "running"]);
const OBSERVED_STATES = new Set([
  "stopped",
  "starting",
  "running",
  "stopping",
  "error",
]);
const SEARCH_DEFAULTS_STATES = new Set([
  "applied",
  "failed",
  "disabled",
  "pending",
]);

function isNullableString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

const ISO_8601_WITH_TZ =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

function isNullableIsoTimestamp(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  return (
    typeof value === "string" &&
    ISO_8601_WITH_TZ.test(value) &&
    !Number.isNaN(Date.parse(value))
  );
}

function isValidSearchDefaults(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value !== "object" || Array.isArray(value)) return false;
  const sd = value as Record<string, unknown>;
  if (typeof sd.state !== "string" || !SEARCH_DEFAULTS_STATES.has(sd.state)) {
    return false;
  }
  if (typeof sd.runtime_instance_id !== "string") return false;
  if (typeof sd.updated_at !== "string") return false;
  if (!isNullableString(sd.error_kind)) return false;
  if (!isNullableString(sd.request_id)) return false;
  return true;
}

const LAYER_STATES = new Set(["running", "stopped", "missing", "error", "unknown"]);
const TRANSPORT_STATES = new Set(["ready", "recovering", "failed", "unknown"]);
const CONTROL_OWNERS = new Set(["user", "agent"]);

function isValidControl(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value !== "object" || Array.isArray(value)) return false;
  const c = value as Record<string, unknown>;
  if (typeof c.profile_id !== "string") return false;
  if (typeof c.owner !== "string" || !CONTROL_OWNERS.has(c.owner)) {
    return false;
  }
  if (typeof c.generation !== "number") return false;
  if (!isNullableString(c.agent_instance_id)) return false;
  if (!isNullableString(c.agent_session_id)) return false;
  if (!isNullableString(c.handoff_reason)) return false;
  if (!isNullableString(c.handoff_detail)) return false;
  if (typeof c.agent_reclaim_allowed !== "boolean") return false;
  if (typeof c.pending_supervisor_close !== "boolean") return false;
  if (typeof c.updated_at !== "string") return false;
  return true;
}

function isValidTransport(value: unknown): boolean {
  if (value === undefined || value === null) return true;
  if (typeof value !== "object" || Array.isArray(value)) return false;
  const t = value as Record<string, unknown>;
  if (typeof t.profile_id !== "string") return false;
  if (!isNullableString(t.runtime_instance_id)) return false;
  if (typeof t.browser_state !== "string" || !LAYER_STATES.has(t.browser_state)) {
    return false;
  }
  if (typeof t.stream_state !== "string" || !LAYER_STATES.has(t.stream_state)) {
    return false;
  }
  if (
    typeof t.transport_state !== "string" ||
    !TRANSPORT_STATES.has(t.transport_state)
  ) {
    return false;
  }
  if (!isNullableString(t.last_error)) return false;
  if (!isNullableString(t.rejection_code)) return false;
  if (!isNullableString(t.gateway_endpoint)) return false;
  return true;
}

function hasValidCoreFields(e: Record<string, unknown>): boolean {
  if (typeof e.profile_id !== "string" || e.profile_id.length === 0) {
    return false;
  }
  if (typeof e.desired_state !== "string" || !DESIRED_STATES.has(e.desired_state)) {
    return false;
  }
  if (
    typeof e.observed_state !== "string" ||
    !OBSERVED_STATES.has(e.observed_state)
  ) {
    return false;
  }
  if (typeof e.failure_count !== "number") return false;
  if (typeof e.restart_blocked !== "boolean") return false;
  if (typeof e.updated_at !== "string") return false;
  return true;
}

/**
 * Validate a decoded SSE payload against the real event semantics of
 * ProfileRuntimeStatusEvent. Returns the event when it is a legal runtime
 * state, or null when it is malformed/unknown and must not be coerced into
 * runtime state. Every field the generated type marks required
 * (profile_id, desired_state, observed_state, failure_count,
 * restart_blocked, updated_at) must be present with the right type;
 * optional fields are type-checked when present.
 */
export function parseProfileRuntimeEvent(
  raw: unknown,
): ProfileRuntimeEvent | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const e = raw as Record<string, unknown>;
  if (!hasValidCoreFields(e)) return null;
  if (!isNullableString(e.runtime_instance_id)) return null;
  if (!isNullableString(e.last_coordinator_error)) return null;
  if (!isNullableIsoTimestamp(e.last_started_at)) return null;
  if (!isNullableIsoTimestamp(e.last_stopped_at)) return null;
  if (!isNullableString(e.browser_product)) return null;
  if (!isNullableString(e.browser_user_agent)) return null;
  if (!isValidSearchDefaults(e.search_defaults)) return null;
  if (!isValidTransport(e.transport)) return null;
  if (!isValidControl(e.control)) return null;
  return raw as ProfileRuntimeEvent;
}

export function parseProfilePreviewEvent(
  raw: unknown,
): ProfilePreviewEvent | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const e = raw as Record<string, unknown>;
  if (e.event !== "profile_preview") return null;
  if (typeof e.profile_id !== "string" || e.profile_id.length === 0) return null;
  if (typeof e.captured_at !== "string" || e.captured_at.length === 0) return null;
  return raw as ProfilePreviewEvent;
}

export function parseReferenceChangedEvent(
  raw: unknown,
): ReferenceChangedEvent | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const e = raw as Record<string, unknown>;
  if (e.event !== "groups_changed" && e.event !== "proxies_changed") return null;
  if (e.entity_id !== null && typeof e.entity_id !== "string") return null;
  return raw as ReferenceChangedEvent;
}

export interface ProfileEventsClientOptions {
  reconnectIntervalMs?: number;
  maxReconnectIntervalMs?: number;
  onUnauthorized?: () => void;
}

const EVENTS_PATH = "/api/v1/events";

export class ProfileEventsClient {
  private url: string;
  private reconnectIntervalMs: number;
  private maxReconnectIntervalMs: number;
  private currentReconnectInterval: number;
  private onUnauthorized?: () => void;
  private lastEventId: string | null = null;
  private isClosed = true;
  // Connection generation: every start/stop advances it, and only the
  // current generation may deliver events, report errors, or reconnect.
  private generation = 0;
  private abortController: AbortController | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<ProfileEventListener> = new Set();
  private previewListeners: Set<ProfilePreviewEventListener> = new Set();
  private referenceListeners: Set<ReferenceChangedEventListener> = new Set();
  private errorListeners: Set<ProfileErrorListener> = new Set();

  constructor(options: ProfileEventsClientOptions = {}) {
    this.url = EVENTS_PATH;
    this.reconnectIntervalMs = options.reconnectIntervalMs ?? 1000;
    this.maxReconnectIntervalMs = options.maxReconnectIntervalMs ?? 30000;
    this.currentReconnectInterval = this.reconnectIntervalMs;
    this.onUnauthorized = options.onUnauthorized;
  }

  onEvent(listener: ProfileEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onPreviewEvent(listener: ProfilePreviewEventListener): () => void {
    this.previewListeners.add(listener);
    return () => this.previewListeners.delete(listener);
  }

  onReferenceEvent(listener: ReferenceChangedEventListener): () => void {
    this.referenceListeners.add(listener);
    return () => this.referenceListeners.delete(listener);
  }

  setOnUnauthorized(callback?: () => void): void {
    this.onUnauthorized = callback;
  }

  onError(listener: ProfileErrorListener): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  start(): void {
    if (!this.isClosed) return;
    this.isClosed = false;
    const generation = ++this.generation;
    void this.connect(generation);
  }

  close(): void {
    this.stop();
  }

  stop(): void {
    this.isClosed = true;
    this.generation += 1;
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = null;
    }
  }

  getLastEventId(): string | null {
    return this.lastEventId;
  }

  private isCurrent(generation: number): boolean {
    return generation === this.generation && !this.isClosed;
  }

  private async connect(generation: number): Promise<void> {
    if (!this.isCurrent(generation)) return;

    // Same final-URL same-origin rule as ApiClient: never stream events
    // (with credentials) from a cross-origin target.
    const target = resolveSameOriginUrl(this.url);
    if (!target) {
      this.dispatchError(
        new Error("Cross-origin SSE connections are not allowed"),
      );
      this.stop();
      return;
    }

    this.abortController = new AbortController();
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };

    if (this.lastEventId) {
      headers["Last-Event-ID"] = this.lastEventId;
    }

    try {
      const response = await fetch(target.href, {
        method: "GET",
        headers,
        credentials: "include",
        signal: this.abortController.signal,
      });

      if (!this.isCurrent(generation)) return;

      if (response.status === 401) {
        this.onUnauthorized?.();
        this.stop();
        return;
      }
      if (!response.ok) {
        throw new Error(`SSE HTTP error: ${response.status} ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error("No readable stream in response body");
      }

      // Reset reconnect interval upon successful connection
      this.currentReconnectInterval = this.reconnectIntervalMs;

      const decoder = new TextDecoder();
      let buffer = "";
      let currentId: string | null = null;
      let currentEventName = "";
      let currentDataLines: string[] = [];

      const resetFrame = () => {
        currentId = null;
        currentEventName = "";
        currentDataLines = [];
      };

      const flushEvent = () => {
        if (currentDataLines.length === 0) return;
        const fullData = currentDataLines.join("\n");
        if (currentId !== null) {
          this.lastEventId = currentId;
        }
        let parsed: unknown;
        try {
          parsed = JSON.parse(fullData);
        } catch (parseErr) {
          this.dispatchError(parseErr);
          return;
        }
        const eventName = currentEventName || "runtime_state";
        let event: ProfileSseEvent | null = null;
        if (eventName === "profile_preview") {
          event = parseProfilePreviewEvent(parsed);
          if (!event) {
            this.dispatchError(
              new Error("Malformed profile_preview event payload"),
            );
            return;
          }
        } else if (
          eventName === "groups_changed" ||
          eventName === "proxies_changed"
        ) {
          event = parseReferenceChangedEvent(parsed);
          if (!event) {
            this.dispatchError(
              new Error(`Malformed ${eventName} event payload`),
            );
            return;
          }
        } else if (eventName === "runtime_state") {
          event = parseProfileRuntimeEvent(parsed);
          if (!event) {
            this.dispatchError(
              new Error("Malformed runtime_state event payload"),
            );
            return;
          }
        } else {
          return;
        }
        this.dispatchEvent(event);
      };

      const processLine = (line: string) => {
        if (line === "") {
          // End of event
          if (this.isCurrent(generation)) {
            flushEvent();
          }
          resetFrame();
        } else if (line.startsWith("id:")) {
          currentId = line.slice(3).trim();
        } else if (line.startsWith("event:")) {
          currentEventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          let data = line.slice(5);
          if (data.startsWith(" ")) {
            data = data.slice(1);
          }
          currentDataLines.push(data);
        }
      };

      while (this.isCurrent(generation)) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          processLine(line);
        }
      }
      if (!this.isCurrent(generation)) return;
      buffer += decoder.decode();
      if (buffer) {
        const lines = buffer.split(/\r?\n/);
        for (const line of lines) {
          processLine(line);
        }
      }
      if (this.isCurrent(generation)) {
        flushEvent();
      }
    } catch (err: unknown) {
      if (!this.isCurrent(generation)) return;
      this.dispatchError(err);
    } finally {
      if (this.isCurrent(generation)) {
        this.scheduleReconnect(generation);
      }
    }
  }

  private dispatchEvent(event: ProfileSseEvent): void {
    if (isReferenceChangedEvent(event)) {
      for (const listener of this.referenceListeners) {
        try {
          listener(event);
        } catch (err) {
          console.error("Error in SSE reference event listener:", err);
        }
      }
    } else if (isProfilePreviewEvent(event)) {
      for (const listener of this.previewListeners) {
        try {
          listener(event);
        } catch (err) {
          console.error("Error in SSE preview event listener:", err);
        }
      }
    } else {
      for (const listener of this.listeners) {
        try {
          listener(event);
        } catch (err) {
          console.error("Error in SSE event listener:", err);
        }
      }
    }
  }

  private dispatchError(error: unknown): void {
    for (const listener of this.errorListeners) {
      try {
        listener(error);
      } catch (err) {
        console.error("Error in SSE error listener:", err);
      }
    }
  }

  private scheduleReconnect(generation: number): void {
    if (!this.isCurrent(generation) || this.reconnectTimeout) return;

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      if (this.isCurrent(generation)) {
        void this.connect(generation);
      }
    }, this.currentReconnectInterval);

    this.currentReconnectInterval = Math.min(
      this.currentReconnectInterval * 1.5,
      this.maxReconnectIntervalMs,
    );
  }
}

export const defaultSseClient = new ProfileEventsClient();
