import { createBrowserRouter, Navigate, type RouteObject } from "react-router";
import { AppLayout } from "./AppLayout";
import { RequireAuth } from "./RequireAuth";
import { BrowserSessionPage } from "../features/profiles/BrowserSessionPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { ProfileNewPage } from "../features/profiles/ProfileNewPage";
import { ProfileDetailPage } from "../features/profiles/ProfileDetailPage";
import { ProfileFilesPage } from "../features/artifacts/ProfileFilesPage";
import { ProfileAutomationPage } from "../features/automation/ProfileAutomationPage";
import { LoginPage } from "../features/auth/LoginPage";

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
        element: <BrowserSessionPage />,
      },
      {
        path: "settings",
        element: <SettingsPage />,
      },
      {
        path: "profiles/new",
        element: <ProfileNewPage />,
      },
      {
        path: "profiles/:profileId",
        element: <ProfileDetailPage />,
      },
      {
        path: "profiles/:profileId/files",
        element: <ProfileFilesPage />,
      },
      {
        path: "automation/:profileId",
        element: <ProfileAutomationPage />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
];

export const router = createBrowserRouter(routes);
