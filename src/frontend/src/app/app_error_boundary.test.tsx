import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type ReactElement, type ReactNode } from "react";
import {
  createMemoryRouter,
  RouterProvider,
  type RouteObject,
} from "react-router";
import { AppErrorPage, defaultRecoveryActions } from "./AppErrorPage";
import { ErrorBoundary, RouteErrorBoundary } from "./ErrorBoundary";
import { frontendLog } from "../shared/logging";
import { I18nProvider, en, zh } from "../i18n";
import { routes } from "./router";

function Bomb({ marker }: { marker: string }): ReactNode {
  throw new Error(marker);
}

function withI18n(children: ReactNode) {
  return <I18nProvider>{children}</I18nProvider>;
}

let consoleErrorSpy: ReturnType<typeof vi.spyOn> | null = null;

beforeEach(() => {
  localStorage.clear();
  document.documentElement.lang = "";
  consoleErrorSpy = vi
    .spyOn(console, "error")
    .mockImplementation(() => undefined);
});

afterEach(() => {
  consoleErrorSpy?.mockRestore();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("AppErrorPage", () => {
  it("renders localized copy and both recovery actions without exposing error details", () => {
    render(withI18n(<AppErrorPage />));
    expect(screen.getByTestId("app-error-page")).toBeInTheDocument();
    expect(screen.getByText(en.errorBoundaryTitle)).toBeInTheDocument();
    expect(screen.getByText(en.errorBoundaryDescription)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.errorBoundaryReload }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.errorBoundaryBack }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("sensitive");
  });

  it("follows the stored zh locale", () => {
    localStorage.setItem("cbrowser.locale", "zh");
    render(withI18n(<AppErrorPage />));
    expect(screen.getByText(zh.errorBoundaryTitle)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: zh.errorBoundaryReload }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: zh.errorBoundaryBack }),
    ).toBeInTheDocument();
  });

  it("wires the reload and back recovery actions", () => {
    const onReload = vi.fn();
    const onBack = vi.fn();
    render(withI18n(<AppErrorPage onReload={onReload} onBack={onBack} />));
    fireEvent.click(
      screen.getByRole("button", { name: en.errorBoundaryReload }),
    );
    fireEvent.click(screen.getByRole("button", { name: en.errorBoundaryBack }));
    expect(onReload).toHaveBeenCalledTimes(1);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it("defaults to a safe reload and a replace-based return to the environment list", () => {
    const reload = vi
      .spyOn(defaultRecoveryActions, "reload")
      .mockImplementation(() => undefined);
    const back = vi
      .spyOn(defaultRecoveryActions, "back")
      .mockImplementation(() => undefined);
    render(withI18n(<AppErrorPage />));
    fireEvent.click(
      screen.getByRole("button", { name: en.errorBoundaryReload }),
    );
    fireEvent.click(screen.getByRole("button", { name: en.errorBoundaryBack }));
    expect(reload).toHaveBeenCalledTimes(1);
    expect(back).toHaveBeenCalledTimes(1);
  });
});

describe("ErrorBoundary", () => {
  it("covers a provider-layer render exception with the localized error page", () => {
    render(
      <ErrorBoundary>
        <Bomb marker="sensitive-stack-trace-marker" />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("app-error-page")).toBeInTheDocument();
    expect(screen.getByText(en.errorBoundaryTitle)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.errorBoundaryReload }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: en.errorBoundaryBack }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toContain(
      "sensitive-stack-trace-marker",
    );
    expect(document.body.textContent).not.toContain("Bomb");
  });

  it("does not remount or stop a healthy session", () => {
    let mounts = 0;
    let renders = 0;
    function Probe({ value }: { value: number }) {
      useEffect(() => {
        mounts += 1;
      }, []);
      renders += 1;
      return <div data-testid="probe">{value}</div>;
    }
    const view = render(
      <ErrorBoundary>
        <Probe value={1} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("probe")).toHaveTextContent("1");
    expect(screen.queryByTestId("app-error-page")).not.toBeInTheDocument();
    view.rerender(
      <ErrorBoundary>
        <Probe value={2} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("probe")).toHaveTextContent("2");
    expect(mounts).toBe(1);
    expect(renders).toBeGreaterThan(1);
  });
});

describe("ErrorBoundary logging and reset (t058 A27)", () => {
  afterEach(() => {
    frontendLog.clear();
  });

  it("records a render error on the frontend log channel", () => {
    // Earlier cases in this file also throw through a boundary; start clean.
    frontendLog.clear();
    const logError = vi.spyOn(frontendLog, "logError");
    render(
      <ErrorBoundary>
        <Bomb marker="sensitive-stack-trace-marker" />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("app-error-page")).toBeInTheDocument();
    expect(logError).toHaveBeenCalledTimes(1);
    const [error, context] = logError.mock.calls[0]!;
    expect((error as Error).message).toBe("sensitive-stack-trace-marker");
    expect(context).toEqual(
      expect.objectContaining({ source: "ErrorBoundary" }),
    );
    expect((context as { componentStack?: string }).componentStack).toContain(
      "Bomb",
    );
    expect(frontendLog.getEntries()).toHaveLength(1);
    expect(frontendLog.getEntries()[0]!.message).toBe(
      "sensitive-stack-trace-marker",
    );
  });

  it("resets when resetKey changes so a fixed route renders again", () => {
    function MaybeBomb({ explode }: { explode: boolean }): ReactNode {
      if (explode) throw new Error("boom-once");
      return <div data-testid="healthy-content">healthy</div>;
    }
    const view = render(
      <ErrorBoundary resetKey="a">
        <MaybeBomb explode />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("app-error-page")).toBeInTheDocument();

    view.rerender(
      <ErrorBoundary resetKey="b">
        <MaybeBomb explode={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("healthy-content")).toBeInTheDocument();
    expect(screen.queryByTestId("app-error-page")).not.toBeInTheDocument();
  });
});

describe("RouteErrorBoundary (t058 A27, AC-006)", () => {
  afterEach(() => {
    frontendLog.clear();
  });

  it("isolates a route error and recovers on navigation", async () => {
    const logError = vi.spyOn(frontendLog, "logError");
    const testRoutes: RouteObject[] = [
      {
        path: "/boom",
        element: (
          <RouteErrorBoundary>
            <Bomb marker="route-private-detail" />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "/ok",
        element: (
          <RouteErrorBoundary>
            <div data-testid="ok-page">ok</div>
          </RouteErrorBoundary>
        ),
      },
    ];
    const router = createMemoryRouter(testRoutes, {
      initialEntries: ["/boom"],
    });
    render(
      withI18n(<RouterProvider router={router} />),
    );
    expect(await screen.findByTestId("app-error-page")).toBeInTheDocument();
    expect(logError).toHaveBeenCalledTimes(1);

    await act(async () => {
      await router.navigate("/ok");
    });
    expect(await screen.findByTestId("ok-page")).toBeInTheDocument();
    expect(screen.queryByTestId("app-error-page")).not.toBeInTheDocument();
  });

  it("wraps every top-level route of the real router", () => {
    expect(routes.length).toBeGreaterThan(0);
    for (const route of routes) {
      expect((route.element as ReactElement).type).toBe(RouteErrorBoundary);
    }
  });

  it("wraps every nested child route too, so one route's error keeps the layout", () => {
    const parents = routes.filter((route) => route.children !== undefined);
    expect(parents.length).toBeGreaterThan(0);
    for (const parent of parents) {
      expect(parent.children!.length).toBeGreaterThan(0);
      for (const child of parent.children!) {
        expect((child.element as ReactElement).type).toBe(
          RouteErrorBoundary,
        );
      }
    }
  });
});

describe("route error element", () => {
  it("renders the error page for an in-router page render exception", async () => {
    const brokenRoutes: RouteObject[] = [
      {
        path: "/",
        element: <Bomb marker="route-private-detail" />,
        errorElement: <AppErrorPage />,
      },
    ];
    render(
      withI18n(
        <RouterProvider
          router={createMemoryRouter(brokenRoutes, {
            initialEntries: ["/"],
          })}
        />,
      ),
    );
    expect(await screen.findByTestId("app-error-page")).toBeInTheDocument();
    expect(screen.getByText(en.errorBoundaryTitle)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("route-private-detail");
  });

  it("configures a domain error element on every top-level route", () => {
    expect(routes.length).toBeGreaterThan(0);
    for (const route of routes) {
      expect(route.errorElement).toBeDefined();
    }
  });
});
