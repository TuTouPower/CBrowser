import { useRef, useState, type KeyboardEvent } from "react";
import { useI18n } from "../../i18n";
import { Button, Popover, SearchField } from "../../shared/ui";

/**
 * Batch "move to group" menu (t077 AC-004/AC-005): the old fixed
 * bottom button row grew past the viewport with many groups and had
 * no search. The menu is now a Popover anchored to the Move button,
 * so Radix keeps it inside the available viewport; its list scrolls
 * internally and is searchable, with arrow-key navigation.
 */
export function MoveGroupMenu({
  groups,
  pending,
  onMove,
}: {
  /** Only id and name are needed here (same bounded shape as the
   * toolbar's candidate groups, t076 review f006). */
  groups: Array<{ id: string; name: string }>;
  pending: boolean;
  onMove: (groupId: string | null) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLDivElement>(null);

  const normalized = query.trim().toLowerCase();
  const filtered = normalized
    ? groups.filter((item) => item.name.toLowerCase().includes(normalized))
    : groups;
  const ungroupedLabel = t("envFilterUngrouped");
  const ungroupedVisible =
    !normalized || ungroupedLabel.toLowerCase().includes(normalized);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) setQuery("");
  }

  function handlePick(groupId: string | null) {
    setOpen(false);
    setQuery("");
    onMove(groupId);
  }

  // Enter in the search box picks the first visible target.
  function handleSearchKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    const first = filtered[0];
    if (first) handlePick(first.id);
    else if (ungroupedVisible) handlePick(null);
  }

  // Arrow keys move focus between the group buttons; Enter/Space
  // activate the focused button natively; Escape closes and returns
  // focus to the trigger (Radix Popover). The handler lives on the
  // menu root so arrows work from the search box too — except Home
  // and End there, which keep their caret meaning inside the input.
  function handleListKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    if (
      (event.target as HTMLElement).tagName === "INPUT" &&
      (event.key === "Home" || event.key === "End")
    ) {
      return;
    }
    const buttons = Array.from(
      listRef.current?.querySelectorAll("button") ?? [],
    );
    if (buttons.length === 0) return;
    event.preventDefault();
    const current = buttons.indexOf(
      document.activeElement as HTMLButtonElement,
    );
    let next: number;
    if (event.key === "Home") next = 0;
    else if (event.key === "End") next = buttons.length - 1;
    else if (event.key === "ArrowDown")
      next = current < 0 ? 0 : (current + 1) % buttons.length;
    else next = current <= 0 ? buttons.length - 1 : current - 1;
    buttons[next]?.focus();
  }

  return (
    <Popover
      ariaLabel={t("envBatchMove")}
      open={open}
      onOpenChange={handleOpenChange}
      trigger={
        <Button data-testid="env-batch-move" size="sm" disabled={pending}>
          {t("envBatchMove")}
        </Button>
      }
    >
      <div
        data-testid="env-move-menu"
        ref={listRef}
        onKeyDown={handleListKeyDown}
        className="flex flex-1 flex-col gap-sm overflow-hidden"
      >
        <SearchField
          label={t("searchGroups")}
          placeholder={t("searchGroups")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={handleSearchKeyDown}
        />
        {filtered.length === 0 && !ungroupedVisible ? (
          <p className="px-sm py-xs font-ui text-body-sm text-on-surface-muted">
            {t("noMatchingGroups")}
          </p>
        ) : (
          <div className="flex flex-1 flex-col gap-xs overflow-y-auto">
            {filtered.map((item) => (
              <Button
                key={item.id}
                data-testid={`env-move-group-${item.id}`}
                size="sm"
                className="w-full justify-start"
                onClick={() => handlePick(item.id)}
              >
                {item.name}
              </Button>
            ))}
            {ungroupedVisible && (
              <Button
                data-testid="env-move-ungrouped"
                size="sm"
                className="w-full justify-start"
                onClick={() => handlePick(null)}
              >
                {ungroupedLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    </Popover>
  );
}
