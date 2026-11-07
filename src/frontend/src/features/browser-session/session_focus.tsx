import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { JSX, ReactNode } from "react";

export interface SessionFocusState {
  focusMode: boolean;
  setFocusMode: (value: boolean) => void;
}

export const SessionFocusContext = createContext<SessionFocusState | null>(null);

export function SessionFocusProvider({ children }: { children: ReactNode }): JSX.Element {
  const [focusMode, setFocusModeState] = useState(false);
  const setFocusMode = useCallback((value: boolean) => setFocusModeState(value), []);
  const value = useMemo(
    () => ({ focusMode, setFocusMode }),
    [focusMode, setFocusMode],
  );
  return <SessionFocusContext.Provider value={value}>{children}</SessionFocusContext.Provider>;
}

export function useSessionFocus(): SessionFocusState {
  const value = useContext(SessionFocusContext);
  return value ?? { focusMode: false, setFocusMode: () => undefined };
}
