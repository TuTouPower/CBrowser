import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useAuth } from "../features/auth/useAuth";
import { loginRedirectPath } from "../features/auth/redirect";
import { useI18n } from "../i18n";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const { isAuthenticated, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div
        data-testid="auth-loading"
        className="h-screen flex items-center justify-center bg-surface-0 text-gray-500 text-sm"
      >
        {t("loading")}
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={loginRedirectPath(location)} replace />;
  }

  return <>{children}</>;
}
