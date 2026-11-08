import { beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import type { ApiClient } from '../../shared/api/client';
import { ApiClientContext } from '../../shared/api/client_context';
import type { ArtifactResponse } from '../../shared/api/types';
import { ProfileFilesTab } from './ProfileFilesTab';

const artifact: ArtifactResponse = {
  id: 'a1',
  profile_id: 'p1',
  name: 'report.csv',
  size: 2048,
  kind: 'upload',
  state: 'ready',
  content_type: 'text/csv',
  sha256: '0'.repeat(64),
  container_path: '/exchange/uploads/a1/report.csv',
  created_at: '2026-01-01T00:00:00Z',
};

function makeStubClient() {
  return {
    artifacts: {
      list: vi.fn(async () => [artifact]),
      upload: vi.fn(async (_profileId: string, file: File) => ({
        ...artifact,
        id: 'a2',
        name: file.name,
        size: file.size,
      })),
      delete: vi.fn(async () => undefined),
      downloadUrl: vi.fn(
        (profileId: string, artifactId: string) =>
          `/api/v1/profiles/${profileId}/artifacts/${artifactId}`,
      ),
    },
  } as unknown as ApiClient & {
    artifacts: {
      list: ReturnType<typeof vi.fn>;
      upload: ReturnType<typeof vi.fn>;
      delete: ReturnType<typeof vi.fn>;
      downloadUrl: ReturnType<typeof vi.fn>;
    };
  };
}

let stub: ReturnType<typeof makeStubClient>;

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub}>
              <ProfileFilesTab profileId="p1" />
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe('ProfileFilesTab', () => {
  beforeEach(() => {
    localStorage.clear();
    stub = makeStubClient();
  });

  it('renders the artifact list with name, size and time from the API', async () => {
    const view = renderTab();
    const row = await view.findByTestId('artifact-item');
    expect(view.getByTestId('profile-files-tab')).toBeInTheDocument();
    expect(row).toHaveTextContent('report.csv');
    expect(row).toHaveTextContent('2.0 KB');
    expect(row).toHaveTextContent(new Date(artifact.created_at).toLocaleString());
    expect(row).toHaveTextContent('/exchange/uploads/a1/report.csv');
    expect(stub.artifacts.list).toHaveBeenCalledWith('p1');
  });

  it('builds the download link from the same-origin artifact URL', async () => {
    const view = renderTab();
    const download = await view.findByTestId('artifact-download');
    expect(download).toHaveAttribute('href', '/api/v1/profiles/p1/artifacts/a1');
    expect(download).toHaveAttribute('download', 'report.csv');
    expect(stub.artifacts.downloadUrl).toHaveBeenCalledWith('p1', 'a1');
  });

  it('uploads the selected file through the artifact API', async () => {
    const view = renderTab();
    await view.findByTestId('artifact-item');
    const file = new File(['a,b\n'], 'new.csv', { type: 'text/csv' });
    fireEvent.change(view.getByTestId('artifact-upload-input'), {
      target: { files: [file] },
    });
    await waitFor(() =>
      expect(stub.artifacts.upload).toHaveBeenCalledWith(
        'p1',
        file,
        expect.any(String),
      ),
    );
    expect(await view.findByTestId('artifact-success')).toBeInTheDocument();
  });

  it('stops at the first failed upload without leaking file contents', async () => {
    stub.artifacts.upload.mockImplementation(
      async (_profileId: string, file: File) => {
        if (file.name === 'bad.csv') throw new Error('disk full');
        return {
          ...artifact,
          id: `a-${file.name}`,
          name: file.name,
          size: file.size,
        };
      },
    );
    const view = renderTab();
    await view.findByTestId('artifact-item');
    const files = [
      new File(['SECRET-OK'], 'ok.csv', { type: 'text/csv' }),
      new File(['SECRET-BAD'], 'bad.csv', { type: 'text/csv' }),
      new File(['SECRET-LATER'], 'later.csv', { type: 'text/csv' }),
    ];
    fireEvent.change(view.getByTestId('artifact-upload-input'), {
      target: { files },
    });
    const alert = await view.findByTestId('artifact-error');
    expect(stub.artifacts.upload).toHaveBeenCalledTimes(2);
    expect(alert.textContent).toContain('Uploaded 1 file(s)');
    expect(alert.textContent).toContain('bad.csv');
    expect(alert.textContent).toContain('1 file(s) were not uploaded');
    expect(alert.textContent).toContain('disk full');
    expect(alert.textContent).not.toContain('SECRET-OK');
    expect(alert.textContent).not.toContain('SECRET-BAD');
    expect(alert.textContent).not.toContain('SECRET-LATER');
    expect(view.queryByTestId('artifact-success')).not.toBeInTheDocument();
  });

  it('deletes after confirmation and surfaces the delete failure state', async () => {
    stub.artifacts.delete.mockRejectedValueOnce(new Error('disk full'));
    const view = renderTab();
    await view.findByTestId('artifact-item');
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    try {
      fireEvent.click(view.getByTestId('artifact-delete'));
      await waitFor(() =>
        expect(stub.artifacts.delete).toHaveBeenCalledWith(
          'p1',
          'a1',
          expect.any(String),
        ),
      );
      expect(await view.findByTestId('artifact-error')).toHaveTextContent(
        'disk full',
      );
    } finally {
      confirmSpy.mockRestore();
    }
  });
});
