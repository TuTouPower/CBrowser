import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useApiClient } from '../../shared/api/client_context';
import type { GroupResponse } from '../../shared/api/types';
import { groupKeys, useReorderGroupsMutation } from './useProfilesQuery';

export function useGroupReorder(groups: GroupResponse[] | undefined) {
  const client = useApiClient();
  const queryClient = useQueryClient();
  const mutation = useReorderGroupsMutation(client);

  const items = useMemo(() => groups ?? [], [groups]);

  async function reorder(orderedIds: string[]): Promise<void> {
    queryClient.setQueryData<GroupResponse[]>(groupKeys.lists(), (old) => {
      if (!old) return old;
      const byId = new Map(old.map((group) => [group.id, group]));
      const next = orderedIds
        .map((id) => byId.get(id))
        .filter((group): group is GroupResponse => group !== undefined);
      return next.length === orderedIds.length ? next : old;
    });
    try {
      await mutation.mutateAsync({ orderedIds });
    } finally {
      await queryClient.invalidateQueries({ queryKey: groupKeys.lists() });
    }
  }

  async function move(id: string, delta: number): Promise<void> {
    const ids = items.map((group) => group.id);
    const index = ids.indexOf(id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= ids.length) return;
    const current = ids[index];
    const swap = ids[target];
    if (current === undefined || swap === undefined) return;
    const next = [...ids];
    next[index] = swap;
    next[target] = current;
    await reorder(next);
  }

  return {
    items,
    moveUp: (id: string) => move(id, -1),
    moveDown: (id: string) => move(id, 1),
    reorder,
  };
}
