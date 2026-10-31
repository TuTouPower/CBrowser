export interface ProfileRuntimeEvent {
  profile_id: string;
  desired_state: string;
  observed_state: string;
  runtime_instance_id?: string | null;
  failure_count?: number;
  restart_blocked?: boolean;
  last_coordinator_error?: string | null;
  updated_at?: string;
}

export type ProfileEventListener = (event: ProfileRuntimeEvent) => void;
export type ProfileErrorListener = (error: unknown) => void;

export interface ProfileEventsClientOptions {
  url?: string;
  reconnectIntervalMs?: number;
  maxReconnectIntervalMs?: number;
}

export class ProfileEventsClient {
  private url: string;
  private reconnectIntervalMs: number;
  private maxReconnectIntervalMs: number;
  private currentReconnectInterval: number;
  private lastEventId: string | null = null;
  private isClosed = false;
  private abortController: AbortController | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private listeners: Set<ProfileEventListener> = new Set();
  private errorListeners: Set<ProfileErrorListener> = new Set();

  constructor(options: ProfileEventsClientOptions = {}) {
    this.url = options.url || "/api/v1/events";
    this.reconnectIntervalMs = options.reconnectIntervalMs ?? 1000;
    this.maxReconnectIntervalMs = options.maxReconnectIntervalMs ?? 30000;
    this.currentReconnectInterval = this.reconnectIntervalMs;
  }

  onEvent(listener: ProfileEventListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  onError(listener: ProfileErrorListener): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  start(): void {
    this.isClosed = false;
    this.connect();
  }

  close(): void {
    this.stop();
  }

  stop(): void {
    this.isClosed = true;
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

  private async connect(): Promise<void> {
    if (this.isClosed) return;

    this.abortController = new AbortController();
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
    };

    if (this.lastEventId) {
      headers["Last-Event-ID"] = this.lastEventId;
    }

    try {
      const response = await fetch(this.url, {
        method: "GET",
        headers,
        credentials: "include",
        signal: this.abortController.signal,
      });

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
      let currentDataLines: string[] = [];

      while (!this.isClosed) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (line === "") {
            // End of event
            if (currentDataLines.length > 0) {
              const fullData = currentDataLines.join("\n");
              if (currentId !== null) {
                this.lastEventId = currentId;
              }
              try {
                const parsed = JSON.parse(fullData) as ProfileRuntimeEvent;
                this.dispatchEvent(parsed);
              } catch (parseErr) {
                this.dispatchError(parseErr);
              }
            }
            currentId = null;
            currentDataLines = [];
          } else if (line.startsWith("id:")) {
            currentId = line.slice(3).trim();
          } else if (line.startsWith("data:")) {
            let data = line.slice(5);
            if (data.startsWith(" ")) {
              data = data.slice(1);
            }
            currentDataLines.push(data);
          }
        }
      }
    } catch (err: unknown) {
      if (this.isClosed) return;
      this.dispatchError(err);
    } finally {
      if (!this.isClosed) {
        this.scheduleReconnect();
      }
    }
  }

  private dispatchEvent(event: ProfileRuntimeEvent): void {
    for (const listener of this.listeners) {
      try {
        listener(event);
      } catch (err) {
        console.error("Error in SSE event listener:", err);
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

  private scheduleReconnect(): void {
    if (this.isClosed || this.reconnectTimeout) return;

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      this.connect();
    }, this.currentReconnectInterval);

    this.currentReconnectInterval = Math.min(
      this.currentReconnectInterval * 1.5,
      this.maxReconnectIntervalMs,
    );
  }
}

export const defaultSseClient = new ProfileEventsClient();

