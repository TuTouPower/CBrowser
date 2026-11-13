import type { TranslationKey } from "../../i18n";
import type { StatusTone } from "../../shared/ui";

/**
 * The backend transport_state is a closed machine enum
 * ("ready" | "recovering" | "failed" | "unknown"). The UI never shows
 * the raw machine value: every surface (session header badge, details
 * panel row) renders the localized label from this single mapping, and
 * any missing or out-of-enum value falls back to the localized
 * "unknown" label instead of leaking the raw code (t061 AC-004).
 */
export function transportStateLabelKey(
  state: string | null | undefined,
): TranslationKey {
  switch (state) {
    case "ready":
      return "transportStateReady";
    case "recovering":
      return "transportStateRecovering";
    case "failed":
      return "transportStateFailed";
    default:
      return "transportStateUnknown";
  }
}

export function transportStateTone(
  state: string | null | undefined,
): StatusTone {
  switch (state) {
    case "ready":
      return "running";
    case "recovering":
      return "transition";
    case "failed":
      return "error";
    default:
      return "stopped";
  }
}
