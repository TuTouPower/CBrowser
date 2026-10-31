import { BrowserSessionView } from "../../features/browser-session/BrowserSessionView";

export interface BrowserSessionViewProps {
  profileId: string;
  onCheckRuntimeStatus?: () => void;
}

export function BrowserSessionMount({
  profileId,
  onCheckRuntimeStatus,
}: BrowserSessionViewProps) {
  return (
    <div
      data-testid="browser-session-mount"
      className="flex-1 flex flex-col min-h-0 w-full h-full relative"
    >
      <BrowserSessionView
        profileId={profileId}
        onCheckRuntimeStatus={onCheckRuntimeStatus}
      />
    </div>
  );
}
