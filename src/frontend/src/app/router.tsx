import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { AppLayout } from "./AppLayout";
import { RequireAuth } from "./RequireAuth";
import { BrowserSessionPage } from "../features/profiles/BrowserSessionPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { ProfileDetailPage } from "../features/profiles/ProfileDetailPage";
import { ProfileFilesPage } from "../features/artifacts/ProfileFilesPage";
import { ProfileAutomationPage } from "../features/automation/ProfileAutomationPage";
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
        element: <PlaceholderPage titleKey="placeholderEnvironments" />,
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
        element: <PlaceholderPage titleKey="placeholderProxies" />,
      },
      {
        path: "profiles/new",
        element: <Navigate to="/" replace />,
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
        element: <ProfileFilesPage />,
      },
      {
        path: "profiles/:profileId/automation",
        element: <ProfileAutomationPage />,
      },
      {
        path: "profiles/:profileId/maintenance",
        element: <PlaceholderPage titleKey="placeholderMaintenance" />,
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
