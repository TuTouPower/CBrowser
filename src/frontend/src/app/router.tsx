import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { AppErrorPage } from "./AppErrorPage";
import { AppLayout } from "./AppLayout";
import { RouteErrorBoundary } from "./ErrorBoundary";
import { RequireAuth } from "./RequireAuth";
import { SessionPage } from "../features/browser-session/SessionPage";
import { SessionEntryPage } from "../features/browser-session/SessionEntryPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { EnvironmentListPage } from "../features/profiles/EnvironmentListPage";
import { ProfileDetailPage } from "../features/profiles/ProfileDetailPage";
import { ProxyListPage } from "../features/proxies/ProxyListPage";
import { LoginPage } from "../features/auth/LoginPage";

export const routes: RouteObject[] = [
  {
    path: "/login",
    element: (
      <RouteErrorBoundary>
        <LoginPage />
      </RouteErrorBoundary>
    ),
    errorElement: <AppErrorPage />,
  },
  {
    path: "/",
    element: (
      <RouteErrorBoundary>
        <RequireAuth>
          <AppLayout />
        </RequireAuth>
      </RouteErrorBoundary>
    ),
    errorElement: <AppErrorPage />,
    children: [
      {
        index: true,
        element: (
          <RouteErrorBoundary>
            <EnvironmentListPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "session",
        element: (
          <RouteErrorBoundary>
            <SessionEntryPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "session/:profileId",
        element: (
          <RouteErrorBoundary>
            <SessionPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "proxies",
        element: (
          <RouteErrorBoundary>
            <ProxyListPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "profiles/:profileId",
        element: (
          <RouteErrorBoundary>
            <Navigate to="config" replace />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "profiles/:profileId/config",
        element: (
          <RouteErrorBoundary>
            <ProfileDetailPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "profiles/:profileId/files",
        element: (
          <RouteErrorBoundary>
            <ProfileDetailPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "profiles/:profileId/automation",
        element: (
          <RouteErrorBoundary>
            <ProfileDetailPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "profiles/:profileId/maintenance",
        element: (
          <RouteErrorBoundary>
            <ProfileDetailPage />
          </RouteErrorBoundary>
        ),
      },
      {
        path: "settings",
        element: (
          <RouteErrorBoundary>
            <SettingsPage />
          </RouteErrorBoundary>
        ),
      },
    ],
  },
  {
    path: "*",
    element: (
      <RouteErrorBoundary>
        <Navigate to="/" replace />
      </RouteErrorBoundary>
    ),
    errorElement: <AppErrorPage />,
  },
];

export const router = createBrowserRouter(routes);
