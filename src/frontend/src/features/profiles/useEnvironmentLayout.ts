import { useCallback, useState } from "react";

const STORAGE_KEY = "cbrowser.environments.layout";

export type EnvironmentLayout = "list" | "card";

export function useEnvironmentLayout(): [
  EnvironmentLayout,
  (layout: EnvironmentLayout) => void,
] {
  const [layout, setLayoutState] = useState<EnvironmentLayout>(() =>
    localStorage.getItem(STORAGE_KEY) === "card" ? "card" : "list",
  );

  const setLayout = useCallback((next: EnvironmentLayout) => {
    setLayoutState(next);
    localStorage.setItem(STORAGE_KEY, next);
  }, []);

  return [layout, setLayout];
}
