import { beforeAll, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import { ApiClientContext } from '../../shared/api/client_context';
import type { ApiClient } from '../../shared/api/client';
import type {
  FontSetInfo,
  GroupResponse,
  ProfileResponse,
  ProfileRuntimeResponse,
  ProxyResponse,
} from '../../shared/api/types';
import { profileKeys } from './useProfilesQuery';
import { ConfigTab } from './ConfigTab';

beforeAll(() => {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal('ResizeObserver', ResizeObserverStub);
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
  }
  if (!window.DOMRect) {
    vi.stubGlobal(
      'DOMRect',
      class {
        constructor(
          public x = 0,
          public y = 0,
          public width = 0,
          public height = 0,
        ) {}
        static fromRect() {
          return new DOMRect();
        }
        top = 0;
        left = 0;
        right = 0;
        bottom = 0;
        toJSON() {
          return {};
        }
      },
    );
  }
  if (!HTMLElement.prototype.hasPointerCapture) {
    HTMLElement.prototype.hasPointerCapture = () => false;
  }
  if (!HTMLElement.prototype.setPointerCapture) {
    HTMLElement.prototype.setPointerCapture = () => undefined;
  }
  if (!HTMLElement.prototype.releasePointerCapture) {
    HTMLElement.prototype.releasePointerCapture = () => undefined;
  }
});

function profile(name = 'Profile Alpha'): ProfileResponse {
  return {
    id: 'p1',
    name,
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

function group(): GroupResponse {
  return {
    id: 'g1',
    name: 'Work',
    color: 'slate',
    sort_order: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function proxy(): ProxyResponse {
  return {
    id: 'px1',
    name: 'Proxy A',
    scheme: 'http',
    host: 'proxy.example',
    port: 8080,
    username: null,
    has_password: false,
    credential_revision: 1,
    proxy_url: 'http://proxy.example:8080',
    country_code: 'US',
    observation_status: 'ok',
    region_label: null,
    notes: null,
    used_by_count: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function fontSet(): FontSetInfo {
  return {
    platform: 'windows',
    set_id: 'fs-1',
    source: 't044',
    source_version: 'v1',
    created_at: '2026-01-01T00:00:00Z',
    integrity: {
      ok: true,
      problems: [],
      missing_fonts: [],
      hash_mismatches: [],
      unregistered_fonts: [],
      file_count: 10,
      detection: {},
    },
    file_count: 10,
    used_by_count: 0,
  };
}

type StubClient = ApiClient & {
  profiles: { get: ReturnType<typeof vi.fn> };
};

function makeStub(get: ReturnType<typeof vi.fn>): StubClient {
  return {
    profiles: {
      get,
      getRuntime: vi.fn(async () => runtime('stopped')),
      list: vi.fn(async () => [profile()]),
      update: vi.fn(async () => profile()),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(async () => profile()),
      reset: vi.fn(async () => profile()),
      retrySearchDefaults: vi.fn(async () => runtime('stopped')),
      setDesiredState: vi.fn(async () => runtime('stopped')),
      stop: vi.fn(async () => runtime('stopped')),
      create: vi.fn(async () => profile()),
    },
    groups: { list: vi.fn(async () => [group()]) },
    proxies: { list: vi.fn(async () => [proxy()]) },
    fontSets: { list: vi.fn(async () => [fontSet()]) },
  } as unknown as StubClient;
}

function renderTab(stub: StubClient) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub}>
              <MemoryRouter>
                <ConfigTab profileId="p1" />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe('ConfigTab', () => {
  it('shows a success echo and remounts with the saved value after save', async () => {
    const initial = profile('Profile Alpha');
    const saved = { ...profile('Renamed By Save'), current_config_version: 2 };
    const get = vi.fn(async () => initial);
    const stub = makeStub(get);
    (stub.profiles.update as ReturnType<typeof vi.fn>).mockResolvedValueOnce(saved);
    const queryClient = renderTab(stub);

    const nameInput = await screen.findByTestId('profile-form-name');
    await waitFor(() => expect(nameInput).toHaveValue('Profile Alpha'));
    fireEvent.change(nameInput, { target: { value: 'Renamed By Save' } });
    fireEvent.click(screen.getByTestId('profile-form-submit'));

    // P2: 保存成功回显 profileUpdatedSuccessfully，且缓存写 saved。
    expect(await screen.findByTestId('profile-config-save-success')).toHaveTextContent(
      'Profile updated successfully.',
    );
    await waitFor(() =>
      expect(queryClient.getQueryData<ProfileResponse>(profileKeys.detail('p1'))).toEqual(
        expect.objectContaining({ name: 'Renamed By Save' }),
      ),
    );
    expect(screen.queryByTestId('profile-config-save-error')).toBeNull();
  });

  it('surfaces a save error without an unhandled rejection', async () => {
    const initial = profile('Profile Alpha');
    const get = vi.fn(async () => initial);
    const stub = makeStub(get);
    (stub.profiles.update as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error('save down'),
    );
    renderTab(stub);

    const nameInput = await screen.findByTestId('profile-form-name');
    fireEvent.change(nameInput, { target: { value: 'Bad Save' } });
    fireEvent.click(screen.getByTestId('profile-form-submit'));

    expect(await screen.findByTestId('profile-config-save-error')).toHaveTextContent(
      'save down',
    );
    expect(screen.queryByTestId('profile-config-save-success')).toBeNull();
  });

  it('keeps unsaved name edits when the profile query is refreshed in the background', async () => {
    const initial = profile('Profile Alpha');
    const pushed = {
      ...profile('Pushed From Backend'),
      current_config_version: 2,
    };
    const fetched = {
      ...profile('Fetched From Backend'),
      current_config_version: 2,
    };
    const get = vi.fn(async () => fetched);
    get.mockResolvedValueOnce(initial);
    const queryClient = renderTab(makeStub(get));

    await screen.findByTestId('profile-config-tab');
    const nameInput = await screen.findByTestId('profile-form-name');
    await waitFor(() => expect(nameInput).toHaveValue('Profile Alpha'));
    expect(
      queryClient.getQueryData<ProfileResponse>(profileKeys.detail('p1')),
    ).toEqual(expect.objectContaining({ name: 'Profile Alpha' }));
    expect(
      screen.queryByTestId('profile-apply-pending'),
    ).not.toBeInTheDocument();

    fireEvent.change(nameInput, { target: { value: 'Unsaved Edit' } });
    expect(screen.getByTestId('profile-form-name')).toHaveValue('Unsaved Edit');

    act(() => {
      queryClient.setQueryData(profileKeys.detail('p1'), pushed);
    });
    expect(
      queryClient.getQueryData<ProfileResponse>(profileKeys.detail('p1')),
    ).toEqual(expect.objectContaining({ name: 'Pushed From Backend' }));
    expect(await screen.findByTestId('profile-apply-pending')).toBeInTheDocument();
    expect(screen.getByTestId('profile-form-name')).toHaveValue('Unsaved Edit');

    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: profileKeys.detail('p1') });
    });
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(get).toHaveBeenCalledWith('p1');
    expect(
      queryClient.getQueryData<ProfileResponse>(profileKeys.detail('p1')),
    ).toEqual(expect.objectContaining({ name: 'Fetched From Backend' }));
    expect(screen.getByTestId('profile-config-tab')).toBeInTheDocument();
    expect(screen.getByTestId('profile-apply-pending')).toBeInTheDocument();
    expect(screen.getByTestId('profile-form-name')).toHaveValue('Unsaved Edit');
  });
});
