import { useState, type FormEvent } from "react";
import { api } from "../lib/api";
import { useI18n } from "../i18n";
import { LanguageToggle } from "./LanguageToggle";

interface LoginPageProps {
  onSuccess: () => void;
}

export function LoginPage({ onSuccess }: LoginPageProps) {
  const { t } = useI18n();
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await api.login(token);
      onSuccess();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("loginFailed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen flex items-center justify-center bg-surface-0">
      <div className="absolute top-4 right-4">
        <LanguageToggle />
      </div>
      <div className="w-80">
        <div className="flex flex-col items-center mb-6">
          <img src="/logo.svg" alt="CBrowser" className="h-12 w-12 mb-3" />
          <h1 className="text-lg font-semibold text-gray-100">
            CBrowser
          </h1>
          <p className="text-xs text-gray-500 mt-1">{t("enterAccessToken")}</p>
        </div>
        <form onSubmit={handleSubmit}>
          <input
            type="password"
            className="input mb-3"
            placeholder={t("accessToken")}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoFocus
          />
          {error && <p className="text-red-400 text-xs mb-3">{error}</p>}
          <button
            type="submit"
            disabled={loading || !token}
            className="btn-primary w-full disabled:opacity-50"
          >
            {loading ? t("authenticating") : t("unlock")}
          </button>
        </form>
      </div>
    </div>
  );
}
