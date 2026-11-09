import { useCallback, useState } from "react";

const STORAGE_KEY = "cbrowser.environments.layout";

export type EnvironmentLayout = "list" | "card";

export function useEnvironmentLayout(): [
  EnvironmentLayout,
  (layout: EnvironmentLayout) => void,
] {
  const [layout, setLayoutState] = useState<EnvironmentLayout>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "card" ? "card" : "list";
    } catch {
      return "list";
    }
  });

  const setLayout = useCallback((next: EnvironmentLayout) => {
    setLayoutState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      return;
    }
  }, []);

  return [layout, setLayout];
}
