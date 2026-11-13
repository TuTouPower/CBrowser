import { useEffect, useState } from "react";
import type { JSX } from "react";
import { Clipboard } from "lucide-react";
import { useI18n } from "../../i18n";
import {
  watchClipboardPermission,
  type ClipboardPermissionState,
} from "./clipboard_bridge";
import { sessId } from "./session_keys";

export function ClipboardPermissionHint(): JSX.Element {
  const { t } = useI18n();
  const [state, setState] = useState<ClipboardPermissionState | null>(null);

  useEffect(() => {
    let cleanup: (() => void) | undefined;
    let active = true;
    void watchClipboardPermission((next) => {
      if (active) setState(next);
    }).then((stop) => {
      if (active) cleanup = stop;
      else stop();
    });
    return () => {
      active = false;
      cleanup?.();
    };
  }, []);

  if (state !== "denied" && state !== "prompt") return <></>;

  const denied = state === "denied";
  return (
    <div
      data-testid={sessId("clipboard", "hint")}
      data-clipboard-permission={state}
      role="status"
      className="pointer-events-none absolute bottom-md left-md z-10 flex max-w-panel flex-col gap-xs rounded-md border border-outline bg-surface p-md"
    >
      <span className="inline-flex items-center gap-sm font-ui text-label-sm text-on-surface">
        <Clipboard aria-hidden="true" className="size-(--component-icon-md-size) shrink-0" />
        {denied ? t("clipboardPermissionDenied") : t("clipboardPermissionPrompt")}
      </span>
      <span className="font-ui text-body-sm text-on-surface-muted">
        {denied
          ? t("clipboardPermissionDeniedHint")
          : t("clipboardPermissionPromptHint")}
      </span>
    </div>
  );
}
