import { useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";
import { Lock } from "lucide-react";
import { useAuth } from "./useAuth";
import { sanitizeNextPath } from "./redirect";
import { useI18n } from "../../i18n";
import { Banner, Button, FieldLabel, Input } from "../../shared/ui";

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
        className="flex min-h-screen items-center justify-center bg-background font-ui text-body-sm text-on-surface-muted"
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
      className="flex min-h-screen items-center justify-center bg-background px-md"
    >
      <div className="w-full max-w-sm rounded-lg border border-outline bg-surface p-xl">
        <div className="mb-lg flex flex-col items-center">
          <div className="mb-md flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-on-surface">
            <Lock aria-hidden="true" className="h-6 w-6" />
          </div>
          <h1 className="font-ui text-headline-lg text-on-surface">CBrowser</h1>
          <p className="mt-sm font-ui text-body-sm text-on-surface-muted">
            {t("enterAccessToken")}
          </p>
        </div>

        {error && (
          <div className="mb-md">
            <Banner tone="danger">{error}</Banner>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-md">
          <div>
            <FieldLabel htmlFor="login-password">{t("accessToken")}</FieldLabel>
            <Input
              id="login-password"
              data-testid="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              disabled={submitting}
              autoFocus
            />
          </div>

          <Button
            data-testid="login-submit"
            type="submit"
            variant="primary"
            disabled={submitting || !password}
          >
            {submitting ? t("authenticating") : t("unlock")}
          </Button>
        </form>
      </div>
    </div>
  );
}
