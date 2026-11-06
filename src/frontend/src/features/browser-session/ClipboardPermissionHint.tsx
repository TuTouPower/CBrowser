import { useEffect, useState } from "react";
import { Clipboard } from "lucide-react";
import { useI18n } from "../../i18n";
import {
  watchClipboardPermission,
  type ClipboardPermissionState,
} from "./clipboard_bridge";

export function ClipboardPermissionHint() {
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

  if (state !== "denied" && state !== "prompt") return null;

  return (
    <div
      data-testid="clipboard-permission-hint"
      data-clipboard-permission={state}
      className="absolute bottom-12 left-2 z-10 max-w-hint text-[11px] px-2.5 py-2 bg-neutral-800/90 text-neutral-200 rounded border border-neutral-700/70"
      role="status"
    >
      <span className="inline-flex items-center gap-1 font-medium">
        <Clipboard className="h-3.5 w-3.5" />
        {state === "denied" ? t("clipboardPermissionDenied") : t("clipboardPermissionPrompt")}
      </span>
      <span className="block mt-1 text-neutral-400">
        {state === "denied"
          ? t("clipboardPermissionDeniedHint")
          : t("clipboardPermissionPromptHint")}
      </span>
    </div>
  );
}
