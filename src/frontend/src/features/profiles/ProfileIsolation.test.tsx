import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {
  MemoryRouter,
  Route,
  Routes,
  useNavigate,
  type NavigateFunction,
} from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import { ApiClientContext } from '../../shared/api/client_context';
import type { ApiClient } from '../../shared/api/client';
import type {
  ProfileResponse,
  ProfileRuntimeResponse,
} from '../../shared/api/types';
import { EnvironmentListPage } from './EnvironmentListPage';
import { ProfileDetailPage } from './ProfileDetailPage';
import { BrowserSessionPage } from './BrowserSessionPage';

beforeAll(() => {
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => undefined;
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

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

function profile(id: string, name: string): ProfileResponse {
  return {
    id,
    name,
    fingerprint_seed: 101,
    group_id: null,
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
    user_data_dir: `/data/${id}`,
    sort_order: 0,
    current_config_version: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function runtime(
  profileId: string,
  observed: ProfileRuntimeResponse['observed_state'],
): ProfileRuntimeResponse {
  return {
    profile_id: profileId,
    desired_state:
      observed === 'running' || observed === 'starting' ? 'running' : 'stopped',
    observed_state: observed,
    runtime_instance_id: 'inst-1',
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    last_started_at: null,
    last_stopped_at: null,
    last_coordinator_error: null,
    updated_at: '2026-01-01T10:00:00Z',
  };
}

const PROFILES = [profile('pA', 'Alpha'), profile('pB', 'Beta')];

interface StubOptions {
  setDesiredStateImpl?: (
    id: string,
    state: 'running' | 'stopped',
  ) => Promise<ProfileRuntimeResponse>;
}

function makeStub(options: StubOptions = {}) {
  const spies = {
    profiles: {
      list: vi.fn(async () => PROFILES),
      get: vi.fn(
        async (id: string) =>
          PROFILES.find((item) => item.id === id) ?? PROFILES[0]!,
      ),
      getRuntime: vi.fn(async (id: string) => runtime(id, 'stopped')),
      setDesiredState: vi.fn(
        options.setDesiredStateImpl ??
          (async (id: string, state: 'running' | 'stopped') =>
            runtime(id, state === 'running' ? 'running' : 'stopped')),
      ),
      stop: vi.fn(async (id: string) => runtime(id, 'stopped')),
      update: vi.fn(
        async (id: string) =>
          PROFILES.find((item) => item.id === id) ?? PROFILES[0]!,
      ),
      delete: vi.fn(async () => undefined),
      duplicate: vi.fn(
        async (id: string) =>
          PROFILES.find((item) => item.id === id) ?? PROFILES[0]!,
      ),
      reset: vi.fn(
        async (id: string) =>
          PROFILES.find((item) => item.id === id) ?? PROFILES[0]!,
      ),
      retrySearchDefaults: vi.fn(async (id: string) => runtime(id, 'stopped')),
      restoreControl: vi.fn(async () => undefined),
    },
    groups: {
      list: vi.fn(async () => []),
      create: vi.fn(async () => undefined),
      update: vi.fn(async () => undefined),
      remove: vi.fn(async () => undefined),
      reorder: vi.fn(async () => []),
    },
    proxies: {
      list: vi.fn(async () => []),
      get: vi.fn(async () => undefined),
    },
    fontSets: { list: vi.fn(async () => []) },
    artifacts: { list: vi.fn(async () => []) },
    automation: { status: vi.fn(async () => undefined) },
    auth: { session: vi.fn(async () => undefined) },
  };
  return {
    client: spies as unknown as ApiClient,
    spies,
  };
}

let navigateFn: NavigateFunction;

function NavCapture() {
  navigateFn = useNavigate();
  return null;
}

function renderPage(client: ApiClient, initialEntry = '/session/pA') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={client}>
              <MemoryRouter initialEntries={[initialEntry]}>
                <NavCapture />
                <Routes>
                  <Route path="/" element={<EnvironmentListPage />} />
                  <Route
                    path="/profiles/:profileId/:tab"
                    element={<ProfileDetailPage />}
                  />
                  <Route
                    path="/session/:profileId"
                    element={<BrowserSessionPage />}
                  />
                </Routes>
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe('AC-011 per-profile action state under the new page structure', () => {
  it("does not show A's launch error on B across the new pages", async () => {
    const { client } = makeStub({
      setDesiredStateImpl: async (id: string) => {
        if (id === 'pA') throw new Error('launch failed A');
        return runtime(id, 'running');
      },
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId('session-launch-btn'));
    expect(await screen.findByTestId('session-start-error')).toHaveTextContent(
      'launch failed A',
    );

    act(() => navigateFn('/session/pB'));
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByTestId('session-start-error')).toBeNull(),
    );

    act(() => navigateFn('/profiles/pB/config'));
    const detail = await screen.findByTestId('profile-detail-view');
    expect(within(detail).queryByText(/launch failed A/)).toBeNull();
    expect(screen.queryByTestId('session-start-error')).toBeNull();
    expect(screen.getByTestId('profile-detail-start')).not.toBeDisabled();
    expect(screen.getByTestId('profile-tab-config')).toBeInTheDocument();

    act(() => navigateFn('/'));
    await screen.findByTestId('env-row-pB');
    const list = screen.getByTestId('env-list-page');
    expect(screen.getByTestId('env-action-start-pB')).not.toBeDisabled();
    expect(list.textContent).not.toContain('launch failed A');
  });

  it("does not disable B's start while A's start is pending", async () => {
    let resolveA!: (value: ProfileRuntimeResponse) => void;
    const pending = new Promise<ProfileRuntimeResponse>((resolve) => {
      resolveA = resolve;
    });
    const { client } = makeStub({
      setDesiredStateImpl: (id: string) => {
        if (id === 'pA') return pending;
        return Promise.resolve(runtime(id, 'running'));
      },
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId('session-launch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('session-launch-btn')).toBeDisabled(),
    );

    act(() => navigateFn('/session/pB'));
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('session-launch-btn')).not.toBeDisabled(),
    );

    act(() => navigateFn('/profiles/pB/config'));
    expect(await screen.findByTestId('profile-detail-view')).toBeInTheDocument();
    expect(screen.getByTestId('profile-detail-start')).not.toBeDisabled();

    act(() => navigateFn('/'));
    await screen.findByTestId('env-row-pB');
    expect(screen.getByTestId('env-list-page')).toBeInTheDocument();
    expect(screen.getByTestId('env-action-start-pB')).not.toBeDisabled();

    await act(async () => {
      resolveA(runtime('pA', 'running'));
    });
  });

  it("does not let A's late failure pollute B's error region", async () => {
    let rejectA!: (err: Error) => void;
    const { client } = makeStub({
      setDesiredStateImpl: (id: string) => {
        if (id === 'pA') {
          return new Promise<ProfileRuntimeResponse>((_resolve, reject) => {
            rejectA = reject;
          });
        }
        return Promise.resolve(runtime(id, 'running'));
      },
    });
    renderPage(client);

    fireEvent.click(await screen.findByTestId('session-launch-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('session-launch-btn')).toBeDisabled(),
    );

    act(() => navigateFn('/session/pB'));
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId('session-launch-btn')).not.toBeDisabled(),
    );

    await act(async () => {
      rejectA(new Error('late A failure'));
    });
    await waitFor(() =>
      expect(screen.queryByTestId('session-start-error')).toBeNull(),
    );
    expect(screen.getByTestId('session-launch-btn')).not.toBeDisabled();

    act(() => navigateFn('/profiles/pB/config'));
    const detail = await screen.findByTestId('profile-detail-view');
    expect(within(detail).queryByText(/late A failure/)).toBeNull();
    expect(screen.getByTestId('profile-detail-start')).not.toBeDisabled();

    act(() => navigateFn('/'));
    await screen.findByTestId('env-row-pB');
    expect(screen.getByTestId('env-list-page')).toBeInTheDocument();
    expect(screen.getByTestId('env-row-pB').textContent).not.toContain(
      'late A failure',
    );
    expect(screen.getByTestId('env-action-start-pB')).not.toBeDisabled();
  });
});

describe('AC-011 independent session target per tab', () => {
  it('writes its own profileId for tab A', async () => {
    const { client } = makeStub();
    const view = renderPage(client, '/session/pA');
    expect(await screen.findByTestId('session-launch-btn')).toBeInTheDocument();
    expect(sessionStorage.getItem('cbrowser.session.target')).toBe('pA');
    view.unmount();
  });

  it('writes its own profileId for a separate tab B without A residue', async () => {
    const first = makeStub();
    const tabA = renderPage(first.client, '/session/pA');
    expect(await screen.findByTestId('session-launch-btn')).toBeInTheDocument();
    expect(sessionStorage.getItem('cbrowser.session.target')).toBe('pA');
    tabA.unmount();
    sessionStorage.clear();

    const second = makeStub();
    const tabB = renderPage(second.client, '/session/pB');
    expect(await screen.findByTestId('session-launch-btn')).toBeInTheDocument();
    expect(sessionStorage.getItem('cbrowser.session.target')).toBe('pB');
    expect(sessionStorage.getItem('cbrowser.session.target')).not.toBe('pA');
    tabB.unmount();
  });

  it('updates the target on profile switch instead of keeping the old value', async () => {
    const { client } = makeStub();
    renderPage(client, '/session/pA');
    expect(await screen.findByTestId('session-launch-btn')).toBeInTheDocument();
    expect(sessionStorage.getItem('cbrowser.session.target')).toBe('pA');

    act(() => navigateFn('/session/pB'));
    expect(await screen.findByText('Beta')).toBeInTheDocument();
    await waitFor(() =>
      expect(sessionStorage.getItem('cbrowser.session.target')).toBe('pB'),
    );
  });
});

describe('AC-011 closing a page does not stop the Profile', () => {
  it('BrowserSessionPage never calls stop on mount, beforeunload or unmount', async () => {
    const { client, spies } = makeStub();
    const view = renderPage(client, '/session/pA');
    expect(await screen.findByTestId('session-launch-btn')).toBeInTheDocument();
    expect(spies.profiles.stop).not.toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new Event('beforeunload'));
    });
    expect(spies.profiles.stop).not.toHaveBeenCalled();

    view.unmount();
    expect(spies.profiles.stop).not.toHaveBeenCalled();
  });

  it('ProfileDetailPage never calls stop on mount, beforeunload or unmount', async () => {
    const { client, spies } = makeStub();
    const view = renderPage(client, '/profiles/pA/config');
    expect(await screen.findByTestId('profile-detail-view')).toBeInTheDocument();
    expect(screen.getByTestId('profile-detail-stop')).toBeInTheDocument();
    expect(spies.profiles.stop).not.toHaveBeenCalled();

    act(() => {
      window.dispatchEvent(new Event('beforeunload'));
    });
    expect(spies.profiles.stop).not.toHaveBeenCalled();

    view.unmount();
    expect(spies.profiles.stop).not.toHaveBeenCalled();
  });
});
