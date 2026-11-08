export const SESS_PAGE = "sess-page";
export const SESS_HEADER = "sess-header";
export const SESS_STAGE = "sess-stage";
export const SESS_IFRAME = "sess-iframe";
export const SESS_ENTRY_PAGE = "sess-entry-page";
export const SESS_ENTRY_LIST = "sess-entry-list";
export const SESS_ENTRY_LINK = "sess-entry-link";
export const SESS_SWITCHER_TRIGGER = "sess-switcher-trigger";
export const SESS_SWITCHER_POPOVER = "sess-switcher-popover";
export const SESS_SWITCHER_SEARCH = "sess-switcher-search";
export const SESS_SWITCHER_GROUP = "sess-switcher-group";
export const SESS_SWITCHER_ITEM = "sess-switcher-item";
export const SESS_DETAILS_PANEL = "sess-details-panel";
export const SESS_DETAILS_TOGGLE = "sess-details-toggle";
export const SESS_FOCUS_TOOLBAR = "sess-focus-toolbar";
export const SESS_FOCUS_EXIT = "sess-focus-exit";
export const SESS_STAGE_PANEL = "sess-stage-panel";
export const SESS_STAGE_TITLE = "sess-stage-title";
export const SESS_STAGE_ACTION = "sess-stage-action";
export const SESS_APPLY_RESTART = "sess-apply-restart";
export const SESS_STOP = "sess-stop";
export const SESS_AUDIO_TOGGLE = "sess-audio-toggle";
export const SESS_DIAG_TOGGLE = "sess-diag-toggle";
export const SESS_COPY_VALUE = "sess-copy-value";

export function sessId(key: string, id: string): string {
  return `sess-${key}-${id}`;
}
