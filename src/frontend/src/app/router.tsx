import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import { AppLayout } from "./AppLayout";
import { RequireAuth } from "./RequireAuth";
import { BrowserSessionPage } from "../features/profiles/BrowserSessionPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { ProfileNewPage } from "../features/profiles/ProfileNewPage";
import { ProfileDetailPage } from "../features/profiles/ProfileDetailPage";
import { ProfileFilesPlaceholder } from "../features/artifacts/ProfileFilesPlaceholder";
import { ProfileAutomationPlaceholder } from "../features/automation/ProfileAutomationPlaceholder";
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
        element: <ProfileFilesPlaceholder />,
      },
      {
        path: "automation/:profileId",
        element: <ProfileAutomationPlaceholder />,
      },
    ],
  },
  {
    path: "*",
    element: <Navigate to="/" replace />,
  },
];

export const router = createBrowserRouter(routes);
