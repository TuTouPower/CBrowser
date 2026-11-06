import { useEffect, useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "../features/auth/useAuth";
import { I18nProvider } from "../i18n";
import { ThemeProvider } from "../theme";
import { ToastProvider } from "../shared/ui";
import { defaultApiClient, ApiClient, shouldRetryRequest } from "../shared/api/client";
import { ApiClientContext } from "../shared/api/client_context";
import { defaultSseClient, ProfileEventsClient } from "../shared/api/sse";
import { useProfileEventsSync } from "../features/profiles/useProfilesQuery";

function SseSyncBridge({ sseClient }: { sseClient: ProfileEventsClient }) {
  const { logout } = useAuth();
  useProfileEventsSync(sseClient);

  useEffect(() => {
    sseClient.setOnUnauthorized?.(() => {
      // Explicit disposal: AuthProvider clears the local auth state in a
      // finally block, so a failed logout request has nothing further to
      // clean up — but its rejection must not escape as an unhandled
      // rejection.
      void logout().catch(() => undefined);
    });
    return () => {
      sseClient.stop();
      sseClient.setOnUnauthorized?.(undefined);
    };
  }, [sseClient, logout]);

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
            retry: shouldRetryRequest,
            refetchOnWindowFocus: true,
          },
          mutations: {
            retry: shouldRetryRequest,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <ToastProvider>
            <ApiClientContext.Provider value={apiClient}>
              <AuthProvider client={apiClient}>
                <AuthenticatedSseBridge sseClient={sseClient} />
                {children}
              </AuthProvider>
            </ApiClientContext.Provider>
          </ToastProvider>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export const Providers = AppProviders;
