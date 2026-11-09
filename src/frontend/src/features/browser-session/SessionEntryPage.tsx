import { Link } from "react-router";
import { useQueries } from "@tanstack/react-query";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { Banner, Button, EmptyState, StatusBadge } from "../../shared/ui";
import { profileKeys, useProfilesQuery } from "../profiles/useProfilesQuery";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

export function SessionEntryPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const profilesQuery = useProfilesQuery(client);
  const profiles = profilesQuery.data ?? [];
  const profilesPending = profilesQuery.isPending;
  const profilesError = profilesQuery.isError
    ? (profilesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;

  const runtimeQueries = useQueries({
    queries: profiles.map((profile) => ({
      queryKey: profileKeys.runtime(profile.id),
      queryFn: () => client.profiles.getRuntime(profile.id),
      // P2: 入口列表运行时查询加 enabled/staleTime，避免空转与抖动。
      enabled: profiles.length > 0,
      staleTime: 5000,
    })),
  });

  const running = profiles.filter((_, index) => {
    const runtime = runtimeQueries[index]?.data as
      | ProfileRuntimeResponse
      | undefined;
    return runtime?.observed_state === "running";
  });
  const runtimeError = runtimeQueries.some((query) => query.isError)
    ? (runtimeQueries.find((query) => query.isError)?.error?.message ??
      t("runtimeStateUnknown"))
    : null;
  const loading =
    profilesPending || runtimeQueries.some((query) => query.isPending);
  const handleRetry = () => {
    if (profilesQuery.isError) void profilesQuery.refetch();
    for (const query of runtimeQueries) {
      if (query.isError) void query.refetch();
    }
  };

  // P2: profiles 失败才整页错误；单个 runtime 失败只顶栏提示，不阻塞
  // 其它运行中环境的列表（避免过度整页错误）。
  const blockingError = profilesError;

  return (
    <div data-testid={SESS_ENTRY_PAGE} className="flex flex-col gap-lg">
      <h1 className="font-ui text-headline-md text-on-surface">
        {t("sessEntryTitle")}
      </h1>
      {blockingError ? (
        <Banner tone="danger" testId="sess-entry-error">
          <span>{blockingError}</span>
          <Button size="sm" data-testid="sess-entry-retry" onClick={handleRetry}>
            {t("retryAction")}
          </Button>
        </Banner>
      ) : (
        <>
          {runtimeError ? (
            <Banner tone="danger" testId="sess-entry-error">
              <span>{runtimeError}</span>
              <Button
                size="sm"
                data-testid="sess-entry-retry"
                onClick={handleRetry}
              >
                {t("retryAction")}
              </Button>
            </Banner>
          ) : null}
          {loading ? (
            <p className="font-ui text-body-md text-on-surface-muted">
              {t("loading")}
            </p>
          ) : running.length === 0 ? (
            <EmptyState
              title={t("sessEntryEmpty")}
              description={t("sessEntryHint")}
            />
          ) : (
            <ul data-testid={SESS_ENTRY_LIST} className="flex flex-col gap-sm">
              {running.map((profile) => (
                <li key={profile.id}>
                  <Link
                    data-testid={SESS_ENTRY_LINK}
                    to={`/session/${encodeURIComponent(profile.id)}`}
                    className="flex items-center justify-between gap-md rounded-md border border-outline bg-surface px-md py-sm font-ui text-body-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                  >
                    <span className="truncate">{profile.name}</span>
                    <StatusBadge tone="running" label={t("sessRunning")} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
