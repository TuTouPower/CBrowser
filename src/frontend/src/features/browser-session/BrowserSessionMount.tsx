import { BrowserSessionView } from "./BrowserSessionView";
import type { BrowserSessionViewProps } from "./types";

/**
 * Layout wrapper for the session view. Lives in the browser-session
 * feature (its only consumer's layer) and reuses the view's own props
 * type instead of redeclaring a drifting subset (A49).
 */
export function BrowserSessionMount(props: BrowserSessionViewProps) {
  return (
    <div
      data-testid="browser-session-mount"
      className="flex-1 flex flex-col min-h-0 w-full h-full relative"
    >
      <BrowserSessionView {...props} />
    </div>
  );
}
