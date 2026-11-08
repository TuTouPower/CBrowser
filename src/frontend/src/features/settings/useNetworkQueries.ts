import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { defaultApiClient, type ApiClient } from "../../shared/api/client";
import type { NetworkAccessSettingsResponse } from "../../shared/api/types";

export const networkKeys = {
  all: ["network"] as const,
  settings: () => [...networkKeys.all, "settings"] as const,
};

export function useNetworkSettingsQuery(
  client: ApiClient = defaultApiClient,
): UseQueryResult<NetworkAccessSettingsResponse, Error> {
  return useQuery({
    queryKey: networkKeys.settings(),
    queryFn: () => client.network.getSettings(),
  });
}
