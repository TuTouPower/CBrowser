import { useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "../features/auth/useAuth";
import { I18nProvider } from "../i18n";
import { defaultApiClient, ApiClient } from "../shared/api/client";
import { defaultSseClient, ProfileEventsClient } from "../shared/api/sse";
import { useProfileEventsSync } from "../features/profiles/useProfilesQuery";

function SseSyncBridge({ sseClient }: { sseClient: ProfileEventsClient }) {
  useProfileEventsSync(sseClient);

  useEffect(() => {
    return () => {
      sseClient.stop();
    };
  }, [sseClient]);

  return null;
}

function AuthenticatedSseBridge({ sseClient }: { sseClient: ProfileEventsClient }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return null;
  return <SseSyncBridge sseClient={sseClient} />;
}

export interface AppProvidersProps {
  children: ReactNode;
  queryClient?: QueryClient;
  apiClient?: ApiClient;
  sseClient?: ProfileEventsClient;
}

export function AppProviders({
  children,
  queryClient: providedQueryClient,
  apiClient = defaultApiClient,
  sseClient = defaultSseClient,
}: AppProvidersProps) {
  const [queryClient] = useState(
    () =>
      providedQueryClient ??
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5000,
            retry: 1,
            refetchOnWindowFocus: true,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider client={apiClient}>
          <AuthenticatedSseBridge sseClient={sseClient} />
          {children}
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export const Providers = AppProviders;
