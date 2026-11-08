import { beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import type { ApiClient } from '../../shared/api/client';
import { ApiClientContext } from '../../shared/api/client_context';
import type {
  AutomationEndpointResponse,
  ProfileControlStateData,
  ProfileRuntimeResponse,
} from '../../shared/api/types';
import { ProfileAutomationTab } from './ProfileAutomationTab';

const automationStatus: AutomationEndpointResponse = {
  profile_id: 'p1',
  cdp_ws_path: '/api/v1/automation/profiles/p1/cdp',
  supervisor_configured: true,
  runtime_observed_state: 'running',
  runtime_instance_id: 'i1',
  token_header: 'Authorization: Bearer <cbat_...>',
};

const userControl: ProfileControlStateData = {
  profile_id: 'p1',
  owner: 'user',
  generation: 4,
  agent_instance_id: 'tok_1',
  agent_session_id: 'exec-1',
  handoff_reason: 'human_input',
  handoff_detail: null,
  agent_reclaim_allowed: false,
  pending_supervisor_close: false,
  updated_at: '2026-11-04T00:00:00Z',
};

const agentControl: ProfileControlStateData = {
  ...userControl,
  owner: 'agent',
  generation: 5,
  handoff_reason: null,
  agent_reclaim_allowed: true,
};

function runtimeWith(
  control: ProfileControlStateData | null,
): ProfileRuntimeResponse {
  return {
    profile_id: 'p1',
    desired_state: 'running',
    observed_state: 'running',
    runtime_instance_id: 'i1',
    config_version: 1,
    failure_count: 0,
    restart_blocked: false,
    last_exit_event_id: null,
    updated_at: '2026-11-04T00:00:00Z',
    control,
  };
}

function makeStubClient(control: ProfileControlStateData | null) {
  let currentControl = control;
  const restoreControl = vi.fn(async () => {
    currentControl = agentControl;
    return agentControl;
  });
  return {
    automation: {
      status: vi.fn(async () => automationStatus),
    },
    profiles: {
      getRuntime: vi.fn(async () => runtimeWith(currentControl)),
      restoreControl,
    },
  } as unknown as ApiClient & {
    automation: { status: ReturnType<typeof vi.fn> };
    profiles: {
      getRuntime: ReturnType<typeof vi.fn>;
      restoreControl: ReturnType<typeof vi.fn>;
    };
  };
}

let stub: ReturnType<typeof makeStubClient>;

function renderTab(control: ProfileControlStateData | null) {
  stub = makeStubClient(control);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={stub}>
              <ProfileAutomationTab profileId="p1" />
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe('ProfileAutomationTab', () => {
  beforeEach(() => {
    localStorage.clear();
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn(async () => undefined) },
    });
  });

  it('renders the authorized endpoint and runtime status', async () => {
    const view = renderTab(null);
    expect(view.getByTestId('profile-automation-tab')).toBeInTheDocument();
    const endpoint = await view.findByTestId('automation-endpoint');
    expect(endpoint.textContent).toMatch(
      /^wss?:\/\/.+\/api\/v1\/automation\/profiles\/p1\/cdp$/,
    );
    const status = view.getByTestId('automation-status');
    expect(status).toHaveTextContent('running');
    expect(status).toHaveTextContent('i1');
    expect(status).toHaveTextContent('Configured');
    expect(view.getByText(/Authorization: Bearer/)).toBeInTheDocument();
    expect(stub.automation.status).toHaveBeenCalledWith('p1');
  });

  it('copies the resolved endpoint into the clipboard', async () => {
    const view = renderTab(null);
    await view.findByTestId('automation-endpoint');
    fireEvent.click(view.getByTestId('automation-copy'));
    await waitFor(() =>
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        expect.stringMatching(
          /^wss?:\/\/.+\/api\/v1\/automation\/profiles\/p1\/cdp$/,
        ),
      ),
    );
    expect(await view.findByText('Copied!')).toBeInTheDocument();
  });

  it('restores agent control through the control API after a human takeover', async () => {
    const view = renderTab(userControl);
    const restore = await view.findByTestId('automation-control-restore');
    expect(view.getByTestId('automation-control-owner')).toHaveTextContent('Human');
    expect(view.getByTestId('automation-control-panel')).toHaveTextContent(
      'human_input',
    );
    fireEvent.click(restore);
    await waitFor(() =>
      expect(stub.profiles.restoreControl).toHaveBeenCalledWith(
        'p1',
        expect.any(String),
      ),
    );
    await waitFor(() =>
      expect(view.getByTestId('automation-control-owner')).toHaveTextContent(
        'Agent',
      ),
    );
  });

  it('hides the control panel when the runtime has no control state', async () => {
    const view = renderTab(null);
    await view.findByTestId('automation-endpoint');
    expect(view.queryByTestId('automation-control-panel')).not.toBeInTheDocument();
  });
});
