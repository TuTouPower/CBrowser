import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider, en } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import { ApiClientContext } from '../../shared/api/client_context';
import { ApiError } from '../../shared/api/client';
import type { ApiClient } from '../../shared/api/client';
import type { ProfileResponse, ProfileRuntimeResponse } from '../../shared/api/types';
import { MaintenanceTab } from './MaintenanceTab';

function profile(): ProfileResponse {
  return {
    id: 'p1',
    name: 'Profile Alpha',
    display_number: 1,
    fingerprint_seed: 101,
    group_id: 'g1',
    proxy_id: null,
    timezone: null,
    locale: null,
    screen_width: 1920,
    screen_height: 1080,
    gpu_family: 'auto',
    humanize: false,
    human_preset: 'default',
    geoip: true,
    clipboard_sync: true,
    auto_launch: false,
    color_scheme: null,
    fingerprint_platform: 'windows',
    font_set_id: null,
    launch_args: [],
    extension_paths: [],
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    notes: null,
    user_data_dir: '/data/p1',
    sort_order: 0,
    current_config_version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function runtime(
  observed: ProfileRuntimeResponse['observed_state'],
): ProfileRuntimeResponse {
  return {
    profile_id: 'p1',
    display_number: 1,
    desired_state: observed === 'stopped' ? 'stopped' : 'running',
    observed_state: observed,
    runtime_instance_id: 'inst_1',
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_started_at: null,
    last_stopped_at: null,
    browser_product: null,
    browser_user_agent: null,
    font_set_id: null,
    missing_fonts: [],
    last_coordinator_error: null,
    search_defaults: null,
    transport: null,
    control: null,
    updated_at: '2026-01-01T00:00:00Z',
  };
}

type StubClient = ApiClient & {
  profiles: {
    getRuntime: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

function makeStub(
  observed: ProfileRuntimeResponse['observed_state'],
): StubClient {
  return {
    profiles: {
      getRuntime: vi.fn(async () => runtime(observed)),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => profile()),
      reset: vi.fn(async () => profile()),
    },
  } as unknown as StubClient;
}

const DETAIL_PATH = '/profiles/p1/maintenance';

function renderTab(client: StubClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  const router = createMemoryRouter(
    [
      { path: '/', element: <div data-testid="env-list-probe" /> },
      { path: DETAIL_PATH, element: <MaintenanceTab profileId="p1" /> },
    ],
    { initialEntries: [DETAIL_PATH] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <RouterProvider router={router} />
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return { invalidateSpy, router };
}

async function clickDelete() {
  // P2: 删除需二次确认：先点请求，再点确认。
  const section = await screen.findByTestId('profile-maintenance-delete');
  const request = within(section).getByTestId('profile-maintenance-delete-request');
  await waitFor(() => expect(request).toBeEnabled());
  fireEvent.click(request);
  const confirm = await within(section).findByTestId('profile-maintenance-delete-confirm');
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
  return confirm;
}

describe('MaintenanceTab', () => {
  it('replaces the deleted profile detail with the environment list', async () => {
    const client = makeStub('stopped');
    const { router } = renderTab(client);

    await clickDelete();
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(router.state.historyAction).toBe('REPLACE');
    expect(await screen.findByTestId('env-list-probe')).toBeInTheDocument();
    expect(
      screen.queryByTestId('profile-maintenance-tab'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('profile-maintenance-error'),
    ).not.toBeInTheDocument();
    expect(client.profiles.delete).toHaveBeenCalledWith('p1', expect.any(String));

    await router.navigate(-1);
    expect(router.state.location.pathname).not.toBe(DETAIL_PATH);
  });

  it('keeps the detail page and the running-disabled error on a 409', async () => {
    const client = makeStub('stopped');
    client.profiles.delete.mockRejectedValue(
      new ApiError('Profile is running', 409, undefined, 'profile_running'),
    );
    const { router } = renderTab(client);

    const button = await clickDelete();
    await waitFor(() =>
      expect(screen.getByTestId('profile-maintenance-error')).toHaveTextContent(
        en.maintenanceDeleteRunningDisabled,
      ),
    );
    expect(router.state.location.pathname).toBe(DETAIL_PATH);
    expect(screen.getByTestId('profile-maintenance-tab')).toBeInTheDocument();

    fireEvent.click(button);
    await waitFor(() =>
      expect(client.profiles.delete).toHaveBeenCalledTimes(2),
    );
    const firstKey = client.profiles.delete.mock.calls[0]![1] as string;
    const secondKey = client.profiles.delete.mock.calls[1]![1] as string;
    expect(firstKey).not.toBe('');
    expect(secondKey).not.toBe('');
    expect(secondKey).not.toBe(firstKey);
  });

  it('keeps the detail page and the API error on a 401', async () => {
    const client = makeStub('stopped');
    client.profiles.delete.mockRejectedValue(
      new ApiError('Unauthorized', 401),
    );
    const { router } = renderTab(client);

    await clickDelete();
    await waitFor(() =>
      expect(screen.getByTestId('profile-maintenance-error')).toHaveTextContent(
        'Unauthorized',
      ),
    );
    expect(router.state.location.pathname).toBe(DETAIL_PATH);
    expect(screen.getByTestId('profile-maintenance-tab')).toBeInTheDocument();
  });

  it('keeps the detail page and the message on a network failure', async () => {
    const client = makeStub('stopped');
    client.profiles.delete.mockRejectedValue(
      new TypeError('Failed to fetch'),
    );
    const { router } = renderTab(client);

    await clickDelete();
    await waitFor(() =>
      expect(screen.getByTestId('profile-maintenance-error')).toHaveTextContent(
        'Failed to fetch',
      ),
    );
    expect(router.state.location.pathname).toBe(DETAIL_PATH);
    expect(screen.getByTestId('profile-maintenance-tab')).toBeInTheDocument();
  });

  it('disables delete while the profile is running', async () => {
    const client = makeStub('running');
    renderTab(client);

    const section = await screen.findByTestId('profile-maintenance-delete');
    const button = within(section).getByRole('button', { name: en.delete });
    await waitFor(() =>
      expect(client.profiles.getRuntime).toHaveBeenCalledWith('p1'),
    );
    expect(button).toBeDisabled();
    expect(
      within(section).getByText(en.maintenanceDeleteRunningDisabled),
    ).toBeInTheDocument();

    fireEvent.click(button);
    expect(client.profiles.delete).not.toHaveBeenCalled();
  });
});
