import { useCallback, useState } from "react";

const STORAGE_KEY = "cbrowser.proxies.layout";

export type ProxyLayout = "list" | "card";

// Layout survives reload via localStorage (t074 AC-003).
export function useProxyLayout(): [ProxyLayout, (layout: ProxyLayout) => void] {
  const [layout, setLayoutState] = useState<ProxyLayout>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "card" ? "card" : "list";
    } catch {
      return "list";
    }
  });

  const setLayout = useCallback((next: ProxyLayout) => {
    setLayoutState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      return;
    }
  }, []);

  return [layout, setLayout];
}
