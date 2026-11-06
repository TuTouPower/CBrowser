import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nProvider } from "../../i18n";
import type { ApiClient } from "../../shared/api/client";
import { ApiClientContext } from "../../shared/api/client_context";
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
  human_preset: "default",
  allow_3p_cookies: true,
  set_google_default: true,
  capture_preview: true,
  restore_session: true,
  transparent_proxy: false,
  portable_cookies: false,
  user_data_dir: "/data/p1",
  sort_order: 0,
  current_config_version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

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

/**
 * A fresh stub per test, injected at the ApiClient boundary (A22). Tests
 * never mutate the production singleton. downloadUrl mirrors the real
 * client's URL format; the format itself is asserted against the real
 * client in client.test.ts.
 */
function makeStubClient() {
  return {
    profiles: {
      get: vi.fn(async () => profile),
    },
    artifacts: {
      list: vi.fn(async () => [artifact]),
      upload: vi.fn(async (_profileId: string, file: File) => ({
        ...artifact,
        id: "a2",
        name: file.name,
        size: file.size,
      })),
      delete: vi.fn(async () => undefined),
      downloadUrl: (profileId: string, artifactId: string) =>
        `/api/v1/profiles/${profileId}/artifacts/${artifactId}`,
    },
  } as unknown as ApiClient & {
    profiles: { get: ReturnType<typeof vi.fn> };
    artifacts: {
      list: ReturnType<typeof vi.fn>;
      upload: ReturnType<typeof vi.fn>;
      delete: ReturnType<typeof vi.fn>;
    };
  };
}

let stub: ReturnType<typeof makeStubClient>;

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
        <ApiClientContext.Provider value={stub}>
          <RouterProvider router={router} />
        </ApiClientContext.Provider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("ProfileFilesPage", () => {
  beforeEach(() => {
    localStorage.clear();
    stub = makeStubClient();
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
    const view = renderPage();
    await view.findByTestId("artifact-row");
    const file = new File(["a,b\n"], "new.csv", { type: "text/csv" });
    fireEvent.change(view.getByTestId("artifact-file-input"), {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(stub.artifacts.upload).toHaveBeenCalledWith(
        "p1",
        file,
        expect.any(String),
      ),
    );
    expect(await view.findByTestId("artifact-notice")).toBeInTheDocument();
  });

  it("stops at the first failed upload and reports succeeded/failed/remaining counts (A20)", async () => {
    stub.artifacts.upload.mockImplementation(
      async (_profileId: string, file: File) => {
        if (file.name === "bad.csv") throw new Error("disk full");
        return { ...artifact, id: `a-${file.name}`, name: file.name, size: file.size };
      },
    );
    const view = renderPage();
    await view.findByTestId("artifact-row");
    // File contents are sentinels unrelated to the file names, so a
    // content leak into the error message is distinguishable (A20).
    const files = [
      new File(["SECRET-CONTENT-OK"], "ok.csv", { type: "text/csv" }),
      new File(["SECRET-CONTENT-BAD"], "bad.csv", { type: "text/csv" }),
      new File(["SECRET-CONTENT-LATER"], "later.csv", { type: "text/csv" }),
    ];
    fireEvent.change(view.getByTestId("artifact-file-input"), {
      target: { files },
    });
    const alert = await view.findByRole("alert");
    // First failure stops the sequence: the third file is never attempted.
    expect(stub.artifacts.upload).toHaveBeenCalledTimes(2);
    expect(alert.textContent).toContain("Uploaded 1 file(s)");
    expect(alert.textContent).toContain("bad.csv");
    expect(alert.textContent).toContain("1 file(s) were not uploaded");
    expect(alert.textContent).toContain("disk full");
    // File contents must never appear in the message.
    expect(alert.textContent).not.toContain("SECRET-CONTENT-OK");
    expect(alert.textContent).not.toContain("SECRET-CONTENT-BAD");
    expect(alert.textContent).not.toContain("SECRET-CONTENT-LATER");
    // The notice for a fully successful batch must not appear.
    expect(view.queryByTestId("artifact-notice")).not.toBeInTheDocument();
  });

  it("deletes an artifact after confirmation and removes its row", async () => {
    let removed = false;
    stub.artifacts.list.mockImplementation(async () => (removed ? [] : [artifact]));
    stub.artifacts.delete.mockImplementation(async () => {
      removed = true;
    });
    const view = renderPage();
    await view.findByTestId("artifact-row");
    const originalConfirm = window.confirm;
    window.confirm = () => true;
    try {
      fireEvent.click(view.getByLabelText("Remove from the profile"));
      await waitFor(() =>
        expect(stub.artifacts.delete).toHaveBeenCalledWith(
          "p1",
          "a1",
          expect.any(String),
        ),
      );
      await waitFor(() =>
        expect(view.queryByTestId("artifact-row")).not.toBeInTheDocument(),
      );
    } finally {
      window.confirm = originalConfirm;
    }
  });
});
