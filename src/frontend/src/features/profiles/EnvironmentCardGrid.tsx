import { EnvironmentCard } from "./EnvironmentCard";
import type { EnvironmentAction, EnvironmentRow } from "./EnvironmentTable";

export function EnvironmentCardGrid({
  rows,
  selected,
  onToggle,
  onAction,
  previewCapturedAtById,
}: {
  rows: EnvironmentRow[];
  selected: Set<string>;
  onToggle: (id: string, checked: boolean) => void;
  onAction: (action: EnvironmentAction, row: EnvironmentRow) => void;
  previewCapturedAtById?: Map<string, string | null>;
}) {
  return (
    <div
      data-testid="env-card-grid"
      className="grid grid-cols-1 gap-lg sm:grid-cols-2 lg:grid-cols-3"
    >
      {rows.map((row) => (
        <EnvironmentCard
          key={row.profile.id}
          row={row}
          selected={selected.has(row.profile.id)}
          onToggle={onToggle}
          onAction={onAction}
          previewCapturedAt={
            previewCapturedAtById?.get(row.profile.id) ?? null
          }
        />
      ))}
    </div>
  );
}
