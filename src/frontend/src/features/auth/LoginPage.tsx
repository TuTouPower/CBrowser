import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Lock } from "lucide-react";
import { useAuth } from "./useAuth";
import { sanitizeNextPath } from "./redirect";
import { useI18n } from "../../i18n";

export function LoginPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isAuthenticated, isLoading, login } = useAuth();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const target = sanitizeNextPath(searchParams.get("next")) ?? "/";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password) return;
    setSubmitting(true);
    setError(null);

    try {
      await login({ password });
      navigate(target, { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("loginFailed"));
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div
        data-testid="auth-loading"
        className="min-h-screen flex items-center justify-center bg-surface-0 text-gray-500 text-sm"
      >
        {t("loading")}
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={target} replace />;
  }

  return (
    <div
      data-testid="login-page"
      className="min-h-screen flex items-center justify-center bg-surface-0 px-4"
    >
      <div className="w-full max-w-sm bg-surface-1 border border-border rounded-lg p-6 shadow-xl">
        <div className="flex flex-col items-center mb-6">
          <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
            <Lock className="h-6 w-6" />
          </div>
          <h1 className="text-xl font-bold text-gray-100">CBrowser v2</h1>
          <p className="text-xs text-gray-400 mt-1">{t("enterAccessToken")}</p>
        </div>

        {error && (
          <div className="mb-4 p-2.5 bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-300 mb-1.5">
              {t("accessToken")}
            </label>
            <input
              data-testid="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              disabled={submitting}
              className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-primary"
              autoFocus
            />
          </div>

          <button
            data-testid="login-submit"
            type="submit"
            disabled={submitting || !password}
            className="w-full py-2 px-4 bg-primary text-primary-foreground font-medium rounded text-sm hover:opacity-90 disabled:opacity-50 transition-opacity"
          >
            {submitting ? t("authenticating") : t("unlock")}
          </button>
        </form>
      </div>
    </div>
  );
}
