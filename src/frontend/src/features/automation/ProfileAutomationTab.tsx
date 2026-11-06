import { useState } from 'react';
import { Check, Copy, Cpu } from 'lucide-react';
import { useI18n } from '../../i18n';
import { useApiClient } from '../../shared/api/client_context';
import {
  Banner,
  Button,
  MonoValue,
  StatusBadge,
  type StatusTone,
} from '../../shared/ui';
import {
  useProfileRuntimeQuery,
  useRestoreControlMutation,
} from '../profiles/useProfilesQuery';
import { useAutomationQuery } from './useAutomation';

function absoluteWebSocketUrl(path: string): string {
  if (typeof window === 'undefined') return path;
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}${path}`;
}

function stateTone(state: string): StatusTone {
  if (state === 'running') return 'running';
  if (state === 'stopped') return 'stopped';
  if (state === 'error') return 'error';
  return 'transition';
}

export function ProfileAutomationTab({ profileId }: { profileId: string }) {
  const { t } = useI18n();
  const client = useApiClient();
  const [copied, setCopied] = useState(false);
  const automation = useAutomationQuery(profileId, client);
  const runtime = useProfileRuntimeQuery(profileId, client);
  const restoreControlMutation = useRestoreControlMutation(client);

  const endpoint = automation.data
    ? absoluteWebSocketUrl(automation.data.cdp_ws_path)
    : '';

  const copyEndpoint = async () => {
    if (!endpoint) return;
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const runtimeState = automation.data?.runtime_observed_state ?? '';
  const stateLabel =
    runtimeState === 'running'
      ? t('statusRunning')
      : runtimeState === 'stopped'
        ? t('statusStopped')
        : runtimeState;

  const control = runtime.data?.control ?? null;

  const handleRestoreControl = () => {
    void restoreControlMutation.mutateAsync(profileId).catch(() => undefined);
  };

  return (
    <div data-testid="profile-automation-tab" className="flex flex-col gap-lg">
      <div>
        <h2 className="flex items-center gap-sm font-ui text-headline-md text-on-surface">
          <Cpu aria-hidden="true" className="h-5 w-5 text-accent" />
          {t('automationPageTitle')}
        </h2>
        <p className="mt-xs font-ui text-body-sm text-on-surface-muted">
          {t('automationPageHint')}
        </p>
      </div>

      {automation.isLoading ? (
        <div className="rounded-lg border border-outline bg-surface px-md py-2xl text-center font-ui text-body-sm text-on-surface-muted">
          {t('loading')}
        </div>
      ) : automation.error ? (
        <Banner tone="danger" testId="automation-error">
          {automation.error.message || t('failedToLoadAutomation')}
        </Banner>
      ) : automation.data ? (
        <>
          <section className="rounded-lg border border-outline bg-surface p-lg">
            <h3 className="mb-sm font-ui text-label-sm text-on-surface-muted">
              {t('automationEndpoint')}
            </h3>
            <div className="flex items-center gap-sm">
              <code
                data-testid="automation-endpoint"
                className="min-w-0 flex-1 truncate rounded-md border border-outline bg-surface-subtle px-md py-sm font-mono text-mono-md text-accent"
              >
                {endpoint}
              </code>
              <Button
                data-testid="automation-copy"
                variant="secondary"
                size="sm"
                aria-label={t('copyEndpoint')}
                onClick={() => void copyEndpoint()}
              >
                {copied ? (
                  <Check aria-hidden="true" className="h-3.5 w-3.5" />
                ) : (
                  <Copy aria-hidden="true" className="h-3.5 w-3.5" />
                )}
                {copied ? t('copied') : t('copy')}
              </Button>
            </div>
            <p className="mt-sm font-ui text-body-sm text-on-surface-muted">
              {t('automationTokenHeader', {
                value: automation.data.token_header,
              })}
            </p>
          </section>

          <section
            data-testid="automation-status"
            className="grid grid-cols-1 gap-md rounded-lg border border-outline bg-surface p-lg sm:grid-cols-3"
          >
            <div>
              <h3 className="mb-sm font-ui text-label-sm text-on-surface-muted">
                {t('automationRuntimeState')}
              </h3>
              <StatusBadge tone={stateTone(runtimeState)} label={stateLabel} />
            </div>
            <div>
              <h3 className="mb-sm font-ui text-label-sm text-on-surface-muted">
                {t('automationRuntimeInstance')}
              </h3>
              <MonoValue>
                {automation.data.runtime_instance_id || '—'}
              </MonoValue>
            </div>
            <div>
              <h3 className="mb-sm font-ui text-label-sm text-on-surface-muted">
                {t('automationSupervisor')}
              </h3>
              <StatusBadge
                tone={
                  automation.data.supervisor_configured ? 'running' : 'stopped'
                }
                label={
                  automation.data.supervisor_configured
                    ? t('automationSupervisorReady')
                    : t('automationSupervisorMissing')
                }
              />
            </div>
          </section>
        </>
      ) : null}

      {control && (
        <section
          data-testid="automation-control-panel"
          className="flex flex-col gap-sm rounded-lg border border-outline bg-surface p-lg"
        >
          <h3 className="font-ui text-title-sm text-on-surface">
            {t('controlTitle')}
          </h3>
          <dl className="flex flex-col gap-sm font-ui text-body-sm">
            <div className="flex gap-sm">
              <dt className="text-on-surface-muted">{t('controlTitle')}:</dt>
              <dd
                data-testid="automation-control-owner"
                className="text-on-surface"
              >
                {control.owner === 'agent'
                  ? t('controlOwnerAgent')
                  : t('controlOwnerUser')}
              </dd>
            </div>
            <div className="flex gap-sm">
              <dt className="text-on-surface-muted">
                {t('controlGeneration')}:
              </dt>
              <dd className="text-on-surface">{control.generation}</dd>
            </div>
            {control.owner === 'user' && control.handoff_reason && (
              <div className="flex gap-sm">
                <dt className="text-on-surface-muted">
                  {t('controlHandoffReason')}:
                </dt>
                <dd className="text-on-surface">{control.handoff_reason}</dd>
              </div>
            )}
            {(control.agent_instance_id || control.agent_session_id) && (
              <div className="flex gap-sm">
                <dt className="text-on-surface-muted">
                  {t('controlAgentIdentity')}:
                </dt>
                <dd className="text-on-surface">
                  <MonoValue>
                    {[
                      control.agent_instance_id,
                      control.agent_session_id,
                    ]
                      .filter(Boolean)
                      .join(' / ')}
                  </MonoValue>
                </dd>
              </div>
            )}
          </dl>
          {control.pending_supervisor_close && (
            <Banner tone="warning">
              {t('controlPendingSupervisorClose')}
            </Banner>
          )}
          {control.owner === 'user' &&
            (control.agent_instance_id || control.agent_session_id) && (
              <Button
                data-testid="automation-control-restore"
                variant="primary"
                size="sm"
                onClick={handleRestoreControl}
                disabled={restoreControlMutation.isPending}
              >
                {restoreControlMutation.isPending
                  ? t('controlRestoring')
                  : t('controlRestore')}
              </Button>
            )}
          {control.owner === 'user' &&
            !control.agent_instance_id &&
            !control.agent_session_id && (
              <p className="font-ui text-body-sm text-on-surface-muted">
                {t('controlNoRecordedAgent')}
              </p>
            )}
          {restoreControlMutation.isError && (
            <Banner tone="danger" testId="automation-control-error">
              {restoreControlMutation.error?.message ||
                t('controlFailedToRestore')}
            </Banner>
          )}
        </section>
      )}
    </div>
  );
}
