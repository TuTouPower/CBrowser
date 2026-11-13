import type { JSX } from "react";
import { useState } from "react";
import { useI18n } from "../../i18n";
import { Button } from "../../shared/ui";
import { SESS_FOCUS_EXIT, SESS_FOCUS_TOOLBAR } from "./session_keys";

export interface FocusModeToolbarProps {
  onExit: () => void;
}

const HOTZONE_ID = "sess-focus-hotzone";

export function FocusModeToolbar(
  props: FocusModeToolbarProps,
): JSX.Element {
  const { onExit } = props;
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);

  return (
    <div
      className="fixed left-none right-none top-none z-50"
      onMouseLeave={() => setVisible(false)}
    >
      <div
        data-testid={HOTZONE_ID}
        aria-hidden="true"
        className="h-(--spacing-sm) w-full"
        onMouseEnter={() => setVisible(true)}
        onMouseMove={() => setVisible(true)}
      />
      {visible && (
        <div
          data-testid={SESS_FOCUS_TOOLBAR}
          className="flex justify-center px-md pb-sm"
        >
          <div className="flex items-center gap-sm rounded-md border border-outline bg-surface-raised px-md py-sm">
            <span className="font-ui text-label-md text-on-surface-muted">
              {t("sessFocus")}
            </span>
            <Button
              size="sm"
              data-testid={SESS_FOCUS_EXIT}
              aria-label={t("sessFocusExit")}
              onMouseDown={(event) => event.stopPropagation()}
              onClick={onExit}
            >
              {t("sessFocusExit")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
