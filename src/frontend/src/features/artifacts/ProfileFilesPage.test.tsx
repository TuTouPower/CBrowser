import { beforeEach, describe, expect, it } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import { defaultApiClient } from "../../shared/api/client";
import type { ArtifactResponse, ProfileResponse } from "../../shared/api/types";
import { ProfileFilesPage } from "./ProfileFilesPage";

const profile: ProfileResponse = {
  id: "p1",
  name: "Profile Alpha",
  fingerprint_seed: 101,
  screen_width: 1920,
  screen_height: 1080,
  gpu_family: "auto",
  humanize: false,
  geoip: false,
  clipboard_sync: false,
  auto_launch: false,
  launch_args: [],
  extension_paths: [],
  tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as ProfileResponse;

const artifact: ArtifactResponse = {
  id: "a1",
  profile_id: "p1",
  name: "report.csv",
  size: 8,
  kind: "upload",
  state: "ready",
  sha256: "0".repeat(64),
  container_path: "/exchange/uploads/a1/report.csv",
  created_at: "2026-01-01T00:00:00Z",
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/profiles/:profileId/files", element: <ProfileFilesPage /> }],
    { initialEntries: ["/profiles/p1/files"] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <RouterProvider router={router} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileFilesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    defaultApiClient.profiles.get = async () => profile;
    defaultApiClient.artifacts.list = async () => [artifact];
    defaultApiClient.artifacts.upload = async (_profileId, file) => ({
      ...artifact,
      id: "a2",
      name: file.name,
      size: file.size,
    });
    defaultApiClient.artifacts.delete = async () => undefined;
  });

  it("lists artifacts with a download link and container path", async () => {
    const view = renderPage();
    expect(await view.findByTestId("artifact-row")).toHaveTextContent("report.csv");
    expect(view.getByTestId("artifact-row")).toHaveTextContent("/exchange/uploads/a1/report.csv");
    const download = view.getByLabelText("Download to this computer");
    expect(download).toHaveAttribute(
      "href",
      "/api/v1/profiles/p1/artifacts/a1",
    );
  });

  it("uploads selected files through the artifact API", async () => {
    let uploaded: File | null = null;
    defaultApiClient.artifacts.upload = async (_profileId, file) => {
      uploaded = file;
      return { ...artifact, id: "a2", name: file.name, size: file.size };
    };
    const view = renderPage();
    await view.findByTestId("artifact-row");
    const file = new File(["a,b\n"], "new.csv", { type: "text/csv" });
    fireEvent.change(view.getByTestId("artifact-file-input"), {
      target: { files: [file] },
    });
    await waitFor(() => expect(uploaded).toBe(file));
    expect(await view.findByTestId("artifact-notice")).toBeInTheDocument();
  });

  it("deletes an artifact after confirmation and removes its row", async () => {
    let deleted: string | null = null;
    let removed = false;
    defaultApiClient.artifacts.list = async () => (removed ? [] : [artifact]);
    defaultApiClient.artifacts.delete = async (_profileId, artifactId) => {
      deleted = artifactId;
      removed = true;
    };
    const view = renderPage();
    await view.findByTestId("artifact-row");
    const originalConfirm = window.confirm;
    window.confirm = () => true;
    try {
      fireEvent.click(view.getByLabelText("Remove from the profile"));
      await waitFor(() => expect(deleted).toBe("a1"));
      await waitFor(() =>
        expect(view.queryByTestId("artifact-row")).not.toBeInTheDocument(),
      );
    } finally {
      window.confirm = originalConfirm;
    }
  });
});
