import { Link } from "react-router";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import { Banner, Button, EmptyState, StatusBadge } from "../../shared/ui";
import {
  useAllProfilesCollectionQuery,
  useRuntimeSummaryQuery,
} from "../profiles/useProfilesQuery";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

export function SessionEntryPage() {
  const { t } = useI18n();
  const client = useApiClient();
  // t076 review f006: the entry page reads the bounded collection
  // page (server-filtered to running) instead of the whole profile
  // table; the running check below keeps the exact "running, not
  // starting" semantics against the batched summary.
  // t076 review f008: the status is the exact running state (the
  // "running" bucket also holds starting rows, which could crowd
  // truly-running rows out of one page), and every page is walked —
  // one 100-row page can never stand in for all running rows.
  const profilesQuery = useAllProfilesCollectionQuery(
    { status: "running_exact", page_size: 100 },
    client,
  );
  const profiles = profilesQuery.data ?? [];
  const profilesPending = profilesQuery.isPending;
  const profilesError = profilesQuery.isError
    ? (profilesQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;

  // t076 AC-002: one batched summary read instead of one runtime
  // request per profile.
  const summaryQuery = useRuntimeSummaryQuery(client);
  const runningIds = new Set(
    (summaryQuery.data?.entries ?? [])
      .filter((entry) => entry.observed_state === "running")
      .map((entry) => entry.profile_id),
  );
  const running = profiles.filter((profile) => runningIds.has(profile.id));
  const runtimeError = summaryQuery.isError
    ? (summaryQuery.error?.message ?? t("runtimeStateUnknown"))
    : null;
  const loading = profilesPending || summaryQuery.isPending;
  const handleRetry = () => {
    if (profilesQuery.isError) void profilesQuery.refetch();
    if (summaryQuery.isError) void summaryQuery.refetch();
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
