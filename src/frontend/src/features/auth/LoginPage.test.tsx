import { describe, it, expect, afterEach, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { I18nProvider } from "../../i18n";
import { AuthProvider } from "./useAuth";
import { LoginPage } from "./LoginPage";
import { ApiError, type ApiClient } from "../../shared/api/client";

function stubClient(loginImpl: () => Promise<void>): ApiClient {
  return {
    auth: {
      login: loginImpl,
      session: async () => ({ authenticated: false }),
      logout: async () => {},
    },
    setOnUnauthorized: () => {},
  } as unknown as ApiClient;
}

function renderLogin(client: ApiClient) {
  return render(
    <I18nProvider>
      <AuthProvider client={client}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </AuthProvider>
    </I18nProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function submitPassword() {
  await waitFor(() =>
    expect(screen.getByTestId("login-password")).toBeInTheDocument(),
  );
  fireEvent.change(screen.getByTestId("login-password"), {
    target: { value: "some-admin-password" },
  });
  fireEvent.click(screen.getByTestId("login-submit"));
}

describe("LoginPage database-unavailable handling (t051 AC-008)", () => {
  it("shows a friendly message for database_busy instead of the raw error", async () => {
    const client = stubClient(async () => {
      throw new ApiError(
        "Database is temporarily locked, retryable operation",
        503,
        { error: "database_busy", retryable: true },
        "database_busy",
        true,
      );
    });
    renderLogin(client);
    await submitPassword();
    await waitFor(() =>
      expect(
        screen.getByText(
          "Database temporarily unavailable. Please try again in a moment.",
        ),
      ).toBeInTheDocument(),
    );
    expect(
      screen.queryByText("Database is temporarily locked, retryable operation"),
    ).not.toBeInTheDocument();
  });

  it("shows the same friendly message for database_unavailable", async () => {
    const client = stubClient(async () => {
      throw new ApiError(
        "Database is temporarily unavailable, retryable operation",
        503,
        { error: "database_unavailable", retryable: true },
        "database_unavailable",
        true,
      );
    });
    renderLogin(client);
    await submitPassword();
    await waitFor(() =>
      expect(
        screen.getByText(
          "Database temporarily unavailable. Please try again in a moment.",
        ),
      ).toBeInTheDocument(),
    );
  });

  it("keeps the existing passthrough for non-database errors", async () => {
    const client = stubClient(async () => {
      throw new ApiError(
        "Invalid credentials",
        401,
        { error: "invalid_credentials", retryable: false },
        "invalid_credentials",
        false,
      );
    });
    renderLogin(client);
    await submitPassword();
    await waitFor(() =>
      expect(screen.getByText("Invalid credentials")).toBeInTheDocument(),
    );
  });
});
