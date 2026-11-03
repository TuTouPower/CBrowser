import {
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  defaultApiClient,
  type ApiClient,
} from "../../shared/api/client";
import { useActionKeyMutation } from "../../shared/api/action_key_mutation";
import type { ArtifactResponse } from "../../shared/api/types";

export const artifactKeys = {
  all: ["artifacts"] as const,
  list: (profileId: string) => [...artifactKeys.all, profileId] as const,
};

export function useArtifactsQuery(
  profileId: string | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<ArtifactResponse[], Error> {
  return useQuery({
    queryKey: artifactKeys.list(profileId || ""),
    queryFn: () => client.artifacts.list(profileId!),
    enabled: Boolean(profileId),
  });
}

export function useUploadArtifactMutation(
  profileId: string | undefined,
  client: ApiClient = defaultApiClient,
): UseMutationResult<ArtifactResponse, Error, File> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.artifacts.upload(profileId!, input, actionKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: artifactKeys.list(profileId || "") });
    },
  });
}

export function useDeleteArtifactMutation(
  profileId: string | undefined,
  client: ApiClient = defaultApiClient,
): UseMutationResult<void, Error, string> {
  const queryClient = useQueryClient();
  return useActionKeyMutation({
    mutationFn: ({ input, actionKey }) =>
      client.artifacts.delete(profileId!, input, actionKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: artifactKeys.list(profileId || "") });
    },
  });
}
