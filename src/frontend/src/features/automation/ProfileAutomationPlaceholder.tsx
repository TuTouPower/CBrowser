import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Cpu } from "lucide-react";

export function ProfileAutomationPlaceholder() {
  const { profileId } = useParams<{ profileId: string }>();

  return (
    <div data-testid="profile-automation-placeholder" className="p-8 max-w-2xl mx-auto">
      <Link
        to={profileId ? `/?profileId=${profileId}` : "/"}
        className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Profile
      </Link>

      <div className="bg-surface-1 border border-border rounded-lg p-8 text-center">
        <Cpu className="h-12 w-12 text-primary/70 mx-auto mb-4" />
        <h2 className="text-lg font-semibold text-gray-100 mb-2">CDP & Automation</h2>
        <p className="text-sm text-gray-400 max-w-md mx-auto mb-4">
          Automated CDP endpoint delegation and headless control tokens for profile{" "}
          <code className="text-primary bg-surface-2 px-1.5 py-0.5 rounded">{profileId}</code>{" "}
          will be delivered in task t008.
        </p>
      </div>
    </div>
  );
}
