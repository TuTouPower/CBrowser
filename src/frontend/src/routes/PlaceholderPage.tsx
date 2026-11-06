import { EmptyState } from "../shared/ui";
import { useI18n, type TranslationKey } from "../i18n";

export function PlaceholderPage({ titleKey }: { titleKey: TranslationKey }) {
  const { t } = useI18n();
  return (
    <div data-testid="placeholder-page">
      <EmptyState title={t(titleKey)} description={t("placeholderComingSoon")} />
    </div>
  );
}
