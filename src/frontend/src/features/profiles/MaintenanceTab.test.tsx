import { describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider, en } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import { ApiClientContext } from '../../shared/api/client_context';
import type { ApiClient } from '../../shared/api/client';
import type { ProfileResponse, ProfileRuntimeResponse } from '../../shared/api/types';
import { profileKeys } from './useProfilesQuery';
import { MaintenanceTab } from './MaintenanceTab';

function profile(): ProfileResponse {
  return {
    id: 'p1',
    name: 'Profile Alpha',
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

function renderTab(client: StubClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter>
                <MaintenanceTab profileId="p1" />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return invalidateSpy;
}

describe('MaintenanceTab', () => {
  it('deletes with a fresh idempotency key per action and keeps the tab mounted after success', async () => {
    const client = makeStub('stopped');
    const invalidateSpy = renderTab(client);

    await screen.findByTestId('profile-maintenance-tab');
    const section = await screen.findByTestId('profile-maintenance-delete');
    const button = within(section).getByRole('button', { name: en.delete });
    await waitFor(() => expect(button).toBeEnabled());
    await waitFor(() =>
      expect(client.profiles.getRuntime).toHaveBeenCalledWith('p1'),
    );

    fireEvent.click(button);
    await waitFor(() =>
      expect(client.profiles.delete).toHaveBeenCalledTimes(1),
    );
    expect(client.profiles.delete).toHaveBeenCalledWith('p1', expect.any(String));
    const firstKey = client.profiles.delete.mock.calls[0]![1] as string;
    expect(firstKey).not.toBe('');

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: profileKeys.lists(),
      }),
    );
    expect(
      screen.queryByTestId('profile-maintenance-error'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('profile-maintenance-delete')).toBeInTheDocument();
    await waitFor(() => expect(button).toBeEnabled());

    fireEvent.click(button);
    await waitFor(() =>
      expect(client.profiles.delete).toHaveBeenCalledTimes(2),
    );
    const secondKey = client.profiles.delete.mock.calls[1]![1] as string;
    expect(secondKey).not.toBe('');
    expect(secondKey).not.toBe(firstKey);
    expect(
      screen.queryByTestId('profile-maintenance-error'),
    ).not.toBeInTheDocument();
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
