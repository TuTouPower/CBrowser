import { BrowserSessionView } from "../../features/browser-session/BrowserSessionView";

export interface BrowserSessionViewProps {
  profileId: string;
  clipboardSync?: boolean;
  onCheckRuntimeStatus?: () => void;
}

export function BrowserSessionMount({
  profileId,
  clipboardSync = true,
  onCheckRuntimeStatus,
}: BrowserSessionViewProps) {
  return (
    <div
      data-testid="browser-session-mount"
      className="flex-1 flex flex-col min-h-0 w-full h-full relative"
    >
      <BrowserSessionView
        profileId={profileId}
        clipboardSync={clipboardSync}
        onCheckRuntimeStatus={onCheckRuntimeStatus}
      />
    </div>
  );
}
