import { beforeEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nProvider } from '../../i18n';
import { ThemeProvider } from '../../theme';
import { ToastProvider } from '../../shared/ui';
import { ApiError, type ApiClient } from '../../shared/api/client';
import { ApiClientContext } from '../../shared/api/client_context';
import type {
  GroupCreateRequest,
  GroupReorderRequest,
  GroupResponse,
  GroupUpdateRequest,
  ProfileResponse,
} from '../../shared/api/types';
import { GroupManagerDialog } from './GroupManagerDialog';

const NOW = '2026-01-01T00:00:00Z';

function makeGroup(
  id: string,
  name: string,
  color: GroupResponse['color'],
  sort_order: number,
): GroupResponse {
  return { id, name, color, sort_order, created_at: NOW, updated_at: NOW };
}

function makeProfile(id: string, groupId: string | null): ProfileResponse {
  return {
    id,
    name: `Profile ${id}`,
    fingerprint_seed: 101,
    screen_width: 1920,
    screen_height: 1080,
    gpu_family: 'auto',
    humanize: false,
    geoip: false,
    clipboard_sync: false,
    auto_launch: false,
    launch_args: [],
    extension_paths: [],
    human_preset: 'default',
    allow_3p_cookies: true,
    set_google_default: true,
    capture_preview: true,
    restore_session: true,
    transparent_proxy: false,
    portable_cookies: false,
    user_data_dir: `/data/${id}`,
    sort_order: 0,
    current_config_version: 1,
    created_at: NOW,
    updated_at: NOW,
    group_id: groupId,
  };
}

const GROUPS: GroupResponse[] = [
  makeGroup('g1', 'Work', 'blue', 0),
  makeGroup('g2', 'Personal', 'green', 1),
];

const GROUPS3: GroupResponse[] = [
  ...GROUPS,
  makeGroup('g3', 'Research', 'amber', 2),
];

const PROFILES: ProfileResponse[] = [
  makeProfile('p1', 'g1'),
  makeProfile('p2', 'g1'),
  makeProfile('p3', 'g2'),
  makeProfile('p4', null),
];

type StubClient = ApiClient & {
  groups: {
    list: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    remove: ReturnType<typeof vi.fn>;
    reorder: ReturnType<typeof vi.fn>;
  };
  profiles: { list: ReturnType<typeof vi.fn> };
};

function makeStub(
  options: {
    groups?: GroupResponse[];
    profiles?: ProfileResponse[];
    createError?: unknown;
  } = {},
): StubClient {
  const groups = options.groups ?? GROUPS;
  const profiles = options.profiles ?? PROFILES;
  return {
    groups: {
      list: vi.fn(async () => groups),
      create: vi.fn(async (data: GroupCreateRequest) => {
        if (options.createError) throw options.createError;
        return makeGroup('g-new', data.name, data.color, groups.length);
      }),
      update: vi.fn(async (id: string, data: GroupUpdateRequest) => {
        const found =
          groups.find((group) => group.id === id) ??
          makeGroup(id, '', 'slate', 0);
        return {
          ...found,
          name: data.name ?? found.name,
          color: data.color ?? found.color,
          sort_order: data.sort_order ?? found.sort_order,
        };
      }),
      remove: vi.fn(async () => undefined),
      reorder: vi.fn(async (_data: GroupReorderRequest) => groups),
    },
    profiles: { list: vi.fn(async () => profiles) },
  } as unknown as StubClient;
}

function renderDialog(client: StubClient) {
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
              <MemoryRouter>
                <GroupManagerDialog open onOpenChange={vi.fn()} />
              </MemoryRouter>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe('GroupManagerDialog', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('lists groups with the number of environments using each', async () => {
    renderDialog(makeStub());
    const rows = await screen.findAllByTestId('group-row');
    expect(rows).toHaveLength(2);
    expect(within(rows[0]!).getByTestId('group-used-by')).toHaveTextContent('Used by 2');
    expect(within(rows[1]!).getByTestId('group-used-by')).toHaveTextContent('Used by 1');
  });

  it('creates a group through client.groups.create with the chosen name and color', async () => {
    const client = makeStub();
    renderDialog(client);
    await screen.findAllByTestId('group-row');
    fireEvent.change(screen.getByTestId('group-new-name'), {
      target: { value: 'Team A' },
    });
    fireEvent.click(
      within(screen.getByTestId('group-new-color')).getByTestId('group-color-teal'),
    );
    fireEvent.click(screen.getByTestId('group-create-submit'));
    await waitFor(() =>
      expect(client.groups.create).toHaveBeenCalledWith(
        { name: 'Team A', color: 'teal', sort_order: 2 },
        expect.any(String),
      ),
    );
  });

  it('renames a group through client.groups.update', async () => {
    const client = makeStub();
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    const row = rows[0]!;
    fireEvent.click(within(row).getByTestId('group-rename-open'));
    fireEvent.change(within(row).getByTestId('group-rename-input'), {
      target: { value: 'Renamed' },
    });
    fireEvent.click(within(row).getByTestId('group-rename-save'));
    await waitFor(() =>
      expect(client.groups.update).toHaveBeenCalledWith(
        'g1',
        { name: 'Renamed' },
        expect.any(String),
      ),
    );
  });

  it('changes a group color through client.groups.update', async () => {
    const client = makeStub();
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    const row = rows[0]!;
    fireEvent.click(within(row).getByTestId('group-color-open'));
    fireEvent.click(within(row).getByTestId('group-color-green'));
    await waitFor(() =>
      expect(client.groups.update).toHaveBeenCalledWith(
        'g1',
        { color: 'green' },
        expect.any(String),
      ),
    );
  });

  it('shows the affected environment count in the delete confirmation and deletes', async () => {
    const client = makeStub();
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    const row = rows[0]!;
    fireEvent.click(within(row).getByTestId('group-delete-open'));
    const confirmation = within(row).getByTestId('group-delete-confirm');
    expect(confirmation).toHaveTextContent(
      'Delete group? 2 environments will become ungrouped',
    );
    expect(
      within(confirmation).getByTestId('group-affected-count'),
    ).toHaveTextContent('2 environments');
    fireEvent.click(within(confirmation).getByTestId('group-delete-accept'));
    await waitFor(() =>
      expect(client.groups.remove).toHaveBeenCalledWith('g1', expect.any(String)),
    );
  });

  it('moves a group up through client.groups.reorder with the correct ordered_ids', async () => {
    const client = makeStub({ groups: GROUPS3 });
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    fireEvent.click(within(rows[1]!).getByTestId('group-reorder-up'));
    await waitFor(() =>
      expect(client.groups.reorder).toHaveBeenCalledWith(
        { ordered_ids: ['g2', 'g1', 'g3'] },
        expect.any(String),
      ),
    );
  });

  it('moves a group down through client.groups.reorder with the correct ordered_ids', async () => {
    const client = makeStub({ groups: GROUPS3 });
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    fireEvent.click(within(rows[0]!).getByTestId('group-reorder-down'));
    await waitFor(() =>
      expect(client.groups.reorder).toHaveBeenCalledWith(
        { ordered_ids: ['g2', 'g1', 'g3'] },
        expect.any(String),
      ),
    );
  });

  it('reorders with ArrowUp/ArrowDown keys', async () => {
    const client = makeStub({ groups: GROUPS3 });
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    fireEvent.keyDown(rows[2]!, { key: 'ArrowUp' });
    await waitFor(() =>
      expect(client.groups.reorder).toHaveBeenCalledWith(
        { ordered_ids: ['g1', 'g3', 'g2'] },
        expect.any(String),
      ),
    );
  });

  it('reorders by dragging a row onto another row', async () => {
    const client = makeStub({ groups: GROUPS3 });
    renderDialog(client);
    const rows = await screen.findAllByTestId('group-row');
    fireEvent.dragStart(rows[0]!);
    fireEvent.dragOver(rows[2]!);
    fireEvent.drop(rows[2]!);
    await waitFor(() =>
      expect(client.groups.reorder).toHaveBeenCalledWith(
        { ordered_ids: ['g2', 'g3', 'g1'] },
        expect.any(String),
      ),
    );
  });

  it('surfaces a 409 group_name_in_use error instead of swallowing it', async () => {
    const client = makeStub({
      createError: new ApiError(
        'Group name already in use',
        409,
        undefined,
        'group_name_in_use',
      ),
    });
    renderDialog(client);
    await screen.findAllByTestId('group-row');
    fireEvent.change(screen.getByTestId('group-new-name'), {
      target: { value: 'Work' },
    });
    fireEvent.click(screen.getByTestId('group-create-submit'));
    const banner = await screen.findByTestId('group-manager-error');
    expect(banner).toHaveTextContent('group_name_in_use');
  });
});
