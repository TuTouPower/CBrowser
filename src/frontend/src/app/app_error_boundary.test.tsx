import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import {
  createMemoryRouter,
  RouterProvider,
  type RouteObject,
} from "react-router";
import { AppErrorPage, defaultRecoveryActions } from "./AppErrorPage";
import { ErrorBoundary } from "./ErrorBoundary";
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
