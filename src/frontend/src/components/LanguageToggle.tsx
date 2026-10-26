import { Languages } from "lucide-react";
import { useI18n, type Locale } from "../i18n";

/** Compact EN / 中文 toggle for the top bar or login page. */
export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  const toggle = () => {
    const next: Locale = locale === "en" ? "zh" : "en";
    setLocale(next);
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={`inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs text-gray-500 hover:text-gray-200 ${className}`}
      title={t("switchLanguage")}
      aria-label={t("switchLanguage")}
    >
      <Languages className="h-3.5 w-3.5" />
      <span className="font-medium">{locale === "en" ? "中文" : "EN"}</span>
    </button>
  );
}
