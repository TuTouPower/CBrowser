import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { AppErrorPage } from "./AppErrorPage";
import { AppLayout } from "./AppLayout";
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
    element: <LoginPage />,
    errorElement: <AppErrorPage />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    errorElement: <AppErrorPage />,
    children: [
      {
        index: true,
        element: <EnvironmentListPage />,
      },
      {
        path: "session",
        element: <SessionEntryPage />,
      },
      {
        path: "session/:profileId",
        element: <SessionPage />,
      },
      {
        path: "proxies",
        element: <ProxyListPage />,
      },
      {
        path: "profiles/:profileId",
        element: <Navigate to="config" replace />,
      },
      {
        path: "profiles/:profileId/config",
        element: <ProfileDetailPage />,
      },
      {
        path: "profiles/:profileId/files",
        element: <ProfileDetailPage />,
      },
      {
        path: "profiles/:profileId/automation",
        element: <ProfileDetailPage />,
      },
      {
        path: "profiles/:profileId/maintenance",
        element: <ProfileDetailPage />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
    errorElement: <AppErrorPage />,
  },
];

export const router = createBrowserRouter(routes);
