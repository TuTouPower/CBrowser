import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { defaultApiClient, type ApiClient } from "../../shared/api/client";
import type { AutomationEndpointResponse } from "../../shared/api/types";

export const automationKeys = {
  all: ["automation"] as const,
  status: (profileId: string) => [...automationKeys.all, profileId] as const,
};

export function useAutomationQuery(
  profileId: string | undefined,
  client: ApiClient = defaultApiClient,
): UseQueryResult<AutomationEndpointResponse, Error> {
  return useQuery({
    queryKey: automationKeys.status(profileId || ""),
    queryFn: () => client.automation.status(profileId!),
    enabled: Boolean(profileId),
  });
}
