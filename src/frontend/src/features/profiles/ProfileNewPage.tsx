import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { useCreateProfileMutation } from "./useProfilesQuery";
import { DEFAULT_PROFILE_CREATE_VALUES } from "../../shared/api/types";
import { useI18n } from "../../i18n";
import { useApiClient } from "../../shared/api/client_context";

export function ProfileNewPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const createMutation = useCreateProfileMutation(useApiClient());

  const [name, setName] = useState("");
  const [screenWidth, setScreenWidth] = useState(1920);
  const [screenHeight, setScreenHeight] = useState(1080);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setError(null);
    try {
      const created = await createMutation.mutateAsync({
        ...DEFAULT_PROFILE_CREATE_VALUES,
        name: name.trim(),
        screen_width: screenWidth,
        screen_height: screenHeight,
      });

      navigate(`/?profileId=${created.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("failedToCreateProfile"));
    }
  };

  return (
    <div data-testid="profile-new-page" className="p-8 max-w-2xl mx-auto">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-xs text-gray-400 hover:text-gray-200 mb-6"
      >
        <ArrowLeft className="h-4 w-4" />
        {t("backToDashboard")}
      </Link>

      <div className="bg-surface-1 border border-border rounded-lg p-6">
        <h1 className="text-lg font-bold text-gray-100 mb-4">{t("newProfile")}</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              {t("profileName")} *
            </label>
            <input
              data-testid="profile-name-input"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("profileNameExample")}
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">
                {t("widthPx")}
              </label>
              <input
                data-testid="profile-width-input"
                type="number"
                value={screenWidth}
                onChange={(e) => setScreenWidth(Number(e.target.value))}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-300 mb-1.5">
                {t("heightPx")}
              </label>
              <input
                data-testid="profile-height-input"
                type="number"
                value={screenHeight}
                onChange={(e) => setScreenHeight(Number(e.target.value))}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 focus:outline-none focus:border-primary"
              />
            </div>
          </div>

          <div className="pt-2 flex justify-end gap-3">
            <Link
              to="/"
              className="px-4 py-2 border border-border text-gray-300 rounded text-sm hover:bg-surface-2"
            >
              {t("cancel")}
            </Link>
            <button
              data-testid="profile-create-submit"
              type="submit"
              disabled={createMutation.isPending || !name.trim()}
              className="px-4 py-2 bg-primary text-primary-foreground font-medium rounded text-sm hover:opacity-90 disabled:opacity-50"
            >
              {createMutation.isPending ? t("saving") : t("create")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
