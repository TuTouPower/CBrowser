import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { AppLayout } from "./AppLayout";
import { RequireAuth } from "./RequireAuth";
import { BrowserSessionPage } from "../features/profiles/BrowserSessionPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { EnvironmentListPage } from "../features/profiles/EnvironmentListPage";
import { ProfileDetailPage } from "../features/profiles/ProfileDetailPage";
import { ProxyListPage } from "../features/proxies/ProxyListPage";
import { LoginPage } from "../features/auth/LoginPage";
import { PlaceholderPage } from "../routes/PlaceholderPage";

export const routes: RouteObject[] = [
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <AppLayout />
      </RequireAuth>
    ),
    children: [
      {
        index: true,
        element: <EnvironmentListPage />,
      },
      {
        path: "session",
        element: <PlaceholderPage titleKey="placeholderSessions" />,
      },
      {
        path: "session/:profileId",
        element: <BrowserSessionPage />,
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
  },
];

export const router = createBrowserRouter(routes);
