import { useQueries } from "@tanstack/react-query";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";
import type { ProfileRuntimeResponse } from "../../shared/api/types";
import { EmptyState, StatusBadge } from "../../shared/ui";
import { profileKeys, useProfilesQuery } from "../profiles/useProfilesQuery";
import { SESS_ENTRY_LINK, SESS_ENTRY_LIST, SESS_ENTRY_PAGE } from "./session_keys";

export function SessionEntryPage() {
  const { t } = useI18n();
  const client = useApiClient();
  const { data: profiles = [], isPending: profilesPending } =
    useProfilesQuery(client);

  const runtimeQueries = useQueries({
    queries: profiles.map((profile) => ({
      queryKey: profileKeys.runtime(profile.id),
      queryFn: () => client.profiles.getRuntime(profile.id),
    })),
  });

  const running = profiles.filter((_, index) => {
    const runtime = runtimeQueries[index]?.data as
      | ProfileRuntimeResponse
      | undefined;
    return runtime?.observed_state === "running";
  });
  const loading =
    profilesPending || runtimeQueries.some((query) => query.isPending);

  return (
    <div data-testid={SESS_ENTRY_PAGE} className="flex flex-col gap-lg">
      <h1 className="font-ui text-headline-md text-on-surface">
        {t("sessEntryTitle")}
      </h1>
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
              <a
                data-testid={SESS_ENTRY_LINK}
                href={`/session/${encodeURIComponent(profile.id)}`}
                className="flex items-center justify-between gap-md rounded-md border border-outline bg-surface px-md py-sm font-ui text-body-md text-on-surface hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
              >
                <span className="truncate">{profile.name}</span>
                <StatusBadge tone="running" label={t("sessRunning")} />
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
