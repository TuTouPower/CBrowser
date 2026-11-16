import { useEffect, useRef } from "react";
import { useApiClient } from "../shared/api/client_context";
import { useAuth } from "../features/auth/useAuth";
import { useI18n } from "../i18n";
import { useTheme } from "../theme";

/**
 * t074 AC-001: server-persisted UI preferences. Kept outside
 * I18nProvider/ThemeProvider so those providers stay independent of auth
 * and the API client (and remain directly renderable in component tests).
 *
 * After login, hydrate theme/locale from the control-plane DB and mirror
 * into localStorage for the first frame. Unauthenticated pages (/login)
 * stay local-only: no 401 request is issued.
 * Every subsequent change (from the settings dialog) is written to the DB.
 */
export function SettingsSync() {
  const client = useApiClient();
  const { isAuthenticated } = useAuth();
  const { locale, setLocale } = useI18n();
  const { preference, setPreference } = useTheme();
  const hydrated = useRef(false);

  useEffect(() => {
    hydrated.current = false;
    if (!isAuthenticated) return;
    let cancelled = false;
    void Promise.resolve()
      .then(() => client.settings.get())
      .then((settings) => {
        if (cancelled) return;
        hydrated.current = true;
        setLocale(settings.locale);
        setPreference(settings.theme);
      })
      .catch(() => {
        hydrated.current = true;
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, client, setLocale, setPreference]);

  useEffect(() => {
    if (!isAuthenticated || !hydrated.current) return;
    void Promise.resolve()
      .then(() => client.settings.update({ locale, theme: preference }))
      .catch(() => undefined);
  }, [locale, preference, isAuthenticated, client]);

  return null;
}
