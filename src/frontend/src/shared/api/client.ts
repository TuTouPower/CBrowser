import type {
  ProfileResponse,
  ProfileCreateRequest,
  ProfileUpdateRequest,
  ProfileRuntimeResponse,
  LoginRequest,
  LoginResponse,
  SessionResponse,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public data?: unknown,
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

export interface ApiClientOptions {
  baseUrl?: string;
  onUnauthorized?: () => void;
}

export class ApiClient {
  private baseUrl: string;
  private onUnauthorized?: () => void;
  private inMemoryCsrfToken: string | null = null;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = options.baseUrl ? options.baseUrl.replace(/\/+$/, "") : "";
    this.onUnauthorized = options.onUnauthorized;
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

  async request<T>(endpoint: string, init: RequestInit = {}): Promise<T> {
    const url = endpoint.startsWith("http")
      ? endpoint
      : `${this.baseUrl}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

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

    const response = await fetch(url, {
      ...init,
      method,
      headers,
      credentials,
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
      } catch {
        // Non-JSON response
      }
      throw new ApiError(errorMessage, response.status, errorData);
    }

    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as unknown as T;
    }

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      return (await response.json()) as T;
    }

    return (await response.text()) as unknown as T;
  }

  readonly profiles = {
    list: async (): Promise<ProfileResponse[]> => {
      return this.request<ProfileResponse[]>("/api/v1/profiles");
    },
    get: async (profileId: string): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(`/api/v1/profiles/${encodeURIComponent(profileId)}`);
    },
    create: async (data: ProfileCreateRequest): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>("/api/v1/profiles", {
        method: "POST",
        body: JSON.stringify(data),
      });
    },
    update: async (profileId: string, data: ProfileUpdateRequest): Promise<ProfileResponse> => {
      return this.request<ProfileResponse>(`/api/v1/profiles/${encodeURIComponent(profileId)}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      });
    },
    delete: async (profileId: string): Promise<void> => {
      await this.request<void>(`/api/v1/profiles/${encodeURIComponent(profileId)}`, {
        method: "DELETE",
      });
    },
    getRuntime: async (profileId: string): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/runtime`,
      );
    },
    setDesiredState: async (
      profileId: string,
      desiredState: "running" | "stopped",
    ): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/runtime/desired-state`,
        {
          method: "PATCH",
          body: JSON.stringify({ desired_state: desiredState }),
        },
      );
    },
    stop: async (profileId: string): Promise<ProfileRuntimeResponse> => {
      return this.request<ProfileRuntimeResponse>(
        `/api/v1/profiles/${encodeURIComponent(profileId)}/stop`,
        {
          method: "POST",
        },
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
      await this.request<void>("/api/v1/auth/logout", {
        method: "POST",
      });
      this.setCsrfToken(null);
    },
    session: async (): Promise<SessionResponse> => {
      const res = await this.request<SessionResponse>("/api/v1/auth/session");
      if (res?.csrf_token) {
        this.setCsrfToken(res.csrf_token);
      }
      return res;
    },
  };

  readonly health = {
    check: async (): Promise<void> => {
      await this.request<void>("/api/v1/health");
    },
  };
}

export const defaultApiClient = new ApiClient();
