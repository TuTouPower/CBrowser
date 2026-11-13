import type {
  ArtifactResponse,
  AutomationEndpointResponse,
  ProfileControlStateData,
  ProfileResponse,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ProfileRuntimeResponse,
  LoginRequest,
  LoginResponse,
  SessionResponse,
  GroupResponse,
  GroupCreateRequest,
  GroupUpdateRequest,
  GroupReorderRequest,
  ProxyResponse,
  ProxyCreateRequest,
  ProxyUpdateRequest,
  FontSetListResponse,
} from "./types";
import { resolveSameOriginUrl } from "./same_origin";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown,
    public errorCode?: string,
    public retryable: boolean = false,
    public detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getCsrfTokenFromCookie(): string | null {
  if (typeof document === "undefined" || !document.cookie) return null;
  const match = document.cookie.match(/(?:^|;\s*)cbrowser_csrf=([^;]*)/);
  return match && match[1] ? decodeURIComponent(match[1]) : null;
}

export function shouldRetryRequest(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.retryable && failureCount < 2;
  }
  return failureCount < 1;
}

export function newIdempotencyKey(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export interface ApiClientOptions {
  onUnauthorized?: () => void;
  defaultTimeoutMs?: number;
  uploadTimeoutMs?: number;
  longOperationTimeoutMs?: number;
}

export class ApiClient {
  private onUnauthorized?: () => void;
  private inMemoryCsrfToken: string | null = null;
  readonly defaultTimeoutMs: number;
  readonly uploadTimeoutMs: number;
  readonly longOperationTimeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.onUnauthorized = options.onUnauthorized;
    this.defaultTimeoutMs = options.defaultTimeoutMs ?? 30_000;
    this.uploadTimeoutMs = options.uploadTimeoutMs ?? 5 * 60_000;
    this.longOperationTimeoutMs = options.longOperationTimeoutMs ?? 120_000;
  }

  setCsrfToken(token: string | null): void {
    this.inMemoryCsrfToken = token;
  }

  getCsrfToken(): string | null {
    return getCsrfTokenFromCookie() || this.inMemoryCsrfToken;
  }

  setOnUnauthorized(callback?: () => void): void {
    this.onUnauthorized = callback;
  }

  async request<T>(
    endpoint: string,
    init: RequestInit = {},
    timeoutMs: number = this.defaultTimeoutMs,
  ): Promise<T> {
    // The same-origin decision is made on the final resolved URL, never
    // on the raw endpoint prefix: backslash and protocol-relative
    // variants normalize to a cross-origin target inside the URL parser
    // and must be refused before credentials or CSRF are attached.
    const target = resolveSameOriginUrl(endpoint);
    if (!target) {
      throw new ApiError("Cross-origin API requests are not allowed", 0);
    }
    const url = target.href;

    const method = (init.method || "GET").toUpperCase();
    const headers = new Headers(init.headers || {});

    // All requests include credentials
    const credentials = init.credentials || "include";

    // For write requests, include X-CSRF-Token
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
      const csrf = this.getCsrfToken();
      if (csrf) {
        headers.set("X-CSRF-Token", csrf);
      }
    }

    if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }

    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const externalSignal = init.signal;
    const onExternalAbort = () => controller.abort();
    if (externalSignal) {
      if (externalSignal.aborted) controller.abort();
      else externalSignal.addEventListener("abort", onExternalAbort, { once: true });
    }
    let response: Response;
    try {
      response = await fetch(url, {
        ...init,
        method,
        headers,
        credentials,
        signal: controller.signal,
      });

      if (response.status === 401) {
        if (this.onUnauthorized) {
          this.onUnauthorized();
        }
      }

      if (!response.ok) {
        let errorMessage = response.statusText || `Request failed with status ${response.status}`;
        let errorData: unknown = null;
        try {
          errorData = await response.json();
          if (
            errorData &&
            typeof errorData === "object" &&
            "detail" in errorData &&
            typeof (errorData as { detail: unknown }).detail === "string"
          ) {
            errorMessage = (errorData as { detail: string }).detail;
          } else if (
            errorData &&
            typeof errorData === "object" &&
            "message" in errorData &&
            typeof (errorData as { message: unknown }).message === "string"
          ) {
            errorMessage = (errorData as { message: string }).message;
          }
        } catch (err) {
          // A body read aborted by the timeout/external signal is not a
          // "non-JSON response": let the outer mapping classify it.
          if (controller.signal.aborted) throw err;
          // Non-JSON response
        }
        const payload =
          errorData && typeof errorData === "object"
            ? (errorData as Record<string, unknown>)
            : undefined;
        throw new ApiError(
          errorMessage,
          response.status,
          errorData,
          typeof payload?.error === "string" ? payload.error : undefined,
          Boolean(payload?.retryable),
          payload?.detail,
        );
      }

      if (response.status === 204 || response.headers.get("content-length") === "0") {
        return undefined as unknown as T;
      }

      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        return (await response.json()) as T;
      }

      return (await response.text()) as unknown as T;
    } catch (err) {
      if (err instanceof ApiError) {
        throw err;
      }
      if (timedOut) {
        throw new ApiError("Request timed out", 0, undefined, "timeout", true);
      }
      if (externalSignal?.aborted) {
        // Caller-initiated cancellation is not a timeout and must not be
        // retried: the caller explicitly abandoned this request.
        throw new ApiError("Request cancelled", 0, undefined, "cancelled", false);
      }
      if (controller.signal.aborted) {
        throw new ApiError("Request timed out", 0, undefined, "timeout", true);
      }
      throw err;
    } finally {
      // The request ends only when the response body has been fully read
      // (or the operation failed): keep the timeout armed and the external
      // abort listener attached until this outermost finally (A18).
      clearTimeout(timer);
      if (externalSignal) {
        externalSignal.removeEventListener("abort", onExternalAbort);
      }
    }
  }

  readonly profiles = {
    list: async (): Promise<ProfileResponse[]> => {
      return this.request<ProfileResponse[]>("/api/v1/profiles");
    },
    get: async (profileId: string): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(`/api/v1/profiles/${encodeURIComponent(profileId)}`);
    },
    create: async (data: ProfileCreateRequest, idempotencyKey?: string): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>("/api/v1/profiles", {
        method: "POST",
        body: JSON.stringify(data),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
    update: async (profileId: string, data: ProfileUpdateRequest, idempotencyKey?: string): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(`/api/v1/profiles/${encodeURIComponent(profileId)}`, {
        method: "PATCH",
        body: JSON.stringify(data),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
    delete: async (profileId: string, idempotencyKey?: string): Promise<void> => {
      await this.request<void>(`/api/v1/profiles/${encodeURIComponent(profileId)}`, {
        method: "DELETE",
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
    getRuntime: async (profileId: string): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/runtime`,
      );
    },
    retrySearchDefaults: async (
      profileId: string,
      idempotencyKey?: string,
    ): Promise<ProfileRuntimeResponse> => {
      // The backend turns the caller's Idempotency-Key into the end-to-end
      // request_id and deduplicates repeats; without a key every call is a
      // fresh execution, so the mutation hook always supplies one (A19).
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/runtime/search-defaults/retry`,
        {
          method: "POST",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    restoreControl: async (
      profileId: string,
      idempotencyKey?: string,
    ): Promise<ProfileControlStateData> => {
      // t031: explicit human restore. Returns the control state; the
      // mutation hook merges it into the cached runtime response.
      return this.request<ProfileControlStateData>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/control/restore`,
        {
          method: "POST",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    setDesiredState: async (
      profileId: string,
      desiredState: "running" | "stopped",
      idempotencyKey?: string,
    ): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/runtime/desired-state`,
        {
          method: "PATCH",
          body: JSON.stringify({ desired_state: desiredState }),
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    stop: async (profileId: string, idempotencyKey?: string): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/stop`,
        {
          method: "POST",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
        this.longOperationTimeoutMs,
      );
    },
    duplicate: async (
      profileId: string,
      data: { include_browser_state: boolean; name?: string },
      idempotencyKey?: string,
    ): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/duplicate`,
        {
          method: "POST",
          body: JSON.stringify(data),
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    reset: async (profileId: string, idempotencyKey?: string): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/reset`,
        {
          method: "POST",
          body: JSON.stringify({ confirm: true }),
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
  };

  readonly artifacts = {
    list: async (profileId: string): Promise<ArtifactResponse[]> => {
      return this.request<ArtifactResponse[]>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/artifacts`,
      );
    },
    upload: async (
      profileId: string,
      file: File,
      idempotencyKey?: string,
    ): Promise<ArtifactResponse> => {
      return this.request<ArtifactResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/artifacts?filename=${encodeURIComponent(file.name)}`,
        {
          method: "POST",
          body: file,
          headers: {
            "Content-Type": file.type || "application/octet-stream",
            ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
          },
        },
        this.uploadTimeoutMs,
      );
    },
    delete: async (
      profileId: string,
      artifactId: string,
      idempotencyKey?: string,
    ): Promise<void> => {
      await this.request<void>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/artifacts/${encodeURIComponent(artifactId)}`,
        {
          method: "DELETE",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    downloadUrl: (profileId: string, artifactId: string): string => {
      const path = `/api/v1/profiles/${encodeURIComponent(profileId)}/artifacts/${encodeURIComponent(artifactId)}`;
      const target = resolveSameOriginUrl(path);
      // The path is built only from encoded ids, so it is same-origin by
      // construction; return the path form so the link can never point
      // at a foreign origin.
      return target ? `${target.pathname}${target.search}` : path;
    },
  };

  readonly automation = {
    status: async (profileId: string): Promise<AutomationEndpointResponse> => {
      return this.request<AutomationEndpointResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/automation`,
      );
    },
  };

  readonly auth = {
    login: async (req: LoginRequest): Promise<LoginResponse> => {
      const res = await this.request<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(req),
      });
      if (res?.csrf_token) {
        this.setCsrfToken(res.csrf_token);
      }
      return res;
    },
    logout: async (): Promise<void> => {
      try {
        await this.request<void>("/api/v1/auth/logout", {
          method: "POST",
        });
      } finally {
        // A failed logout request must not leave a usable CSRF token
        // behind: the local session is over either way.
        this.setCsrfToken(null);
      }
    },
    session: async (): Promise<SessionResponse> => {
      const res = await this.request<SessionResponse>("/api/v1/auth/session");
      if (res?.csrf_token) {
        this.setCsrfToken(res.csrf_token);
      }
      return res;
    },
  };

  readonly groups = {
    list: async (): Promise<GroupResponse[]> => {
      return this.request<GroupResponse[]>("/api/v1/groups");
    },
    create: async (
      data: GroupCreateRequest,
      idempotencyKey?: string,
    ): Promise<GroupResponse> => {
      return this.request<GroupResponse>("/api/v1/groups", {
        method: "POST",
        body: JSON.stringify(data),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
    update: async (
      groupId: string,
      data: GroupUpdateRequest,
      idempotencyKey?: string,
    ): Promise<GroupResponse> => {
      return this.request<GroupResponse>(
        `/api/v1/groups/${encodeURIComponent(groupId)}`,
        {
          method: "PATCH",
          body: JSON.stringify(data),
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    remove: async (groupId: string, idempotencyKey?: string): Promise<void> => {
      await this.request<void>(
        `/api/v1/groups/${encodeURIComponent(groupId)}`,
        {
          method: "DELETE",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    reorder: async (
      data: GroupReorderRequest,
      idempotencyKey?: string,
    ): Promise<GroupResponse[]> => {
      return this.request<GroupResponse[]>("/api/v1/groups/reorder", {
        method: "POST",
        body: JSON.stringify(data),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
  };

  readonly proxies = {
    list: async (): Promise<ProxyResponse[]> => {
      return this.request<ProxyResponse[]>("/api/v1/proxies");
    },
    get: async (proxyId: string): Promise<ProxyResponse> => {
      return this.request<ProxyResponse>(
        `/api/v1/proxies/${encodeURIComponent(proxyId)}`,
      );
    },
    create: async (
      data: ProxyCreateRequest,
      idempotencyKey?: string,
    ): Promise<ProxyResponse> => {
      return this.request<ProxyResponse>("/api/v1/proxies", {
        method: "POST",
        body: JSON.stringify(data),
        headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
      });
    },
    update: async (
      proxyId: string,
      data: ProxyUpdateRequest,
      idempotencyKey?: string,
    ): Promise<ProxyResponse> => {
      return this.request<ProxyResponse>(
        `/api/v1/proxies/${encodeURIComponent(proxyId)}`,
        {
          method: "PATCH",
          body: JSON.stringify(data),
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    remove: async (proxyId: string, idempotencyKey?: string): Promise<void> => {
      await this.request<void>(
        `/api/v1/proxies/${encodeURIComponent(proxyId)}`,
        {
          method: "DELETE",
          headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
        },
      );
    },
    /** Manual egress probe (t052 AC-006): body carries only the proxy id. */
    probe: async (proxyId: string): Promise<ProxyResponse> => {
      return this.request<ProxyResponse>(
        `/api/v1/proxies/${encodeURIComponent(proxyId)}/probe`,
        { method: "POST" },
      );
    },
  };

  readonly fontSets = {
    list: async (): Promise<FontSetListResponse> => {
      return this.request<FontSetListResponse>("/api/v1/font-sets");
    },
  };

  readonly health = {
    check: async (): Promise<void> => {
      await this.request<void>("/api/v1/health");
    },
  };
}

export const defaultApiClient = new ApiClient();
