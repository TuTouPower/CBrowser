import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { X } from "lucide-react";

interface ToastApi {
  show: (message: string) => void;
  dismiss: () => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);

  const show = useCallback((next: string) => setMessage(next), []);
  const dismiss = useCallback(() => setMessage(null), []);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), 4000);
    return () => window.clearTimeout(timer);
  }, [message]);

  const api = useMemo(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        data-testid="toast-viewport"
        role="region"
        aria-label="Notifications"
        className="pointer-events-none fixed bottom-lg right-lg z-[60] flex flex-col gap-sm"
      >
        {message && (
          <div
            data-testid="toast-item"
            role="status"
            aria-live="polite"
            className="pointer-events-auto flex items-center gap-md rounded-lg border border-outline bg-surface-raised px-md py-sm font-ui text-body-sm text-on-surface shadow-lg"
          >
            <span>{message}</span>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={dismiss}
              className="rounded-sm p-xs hover:bg-surface-hover focus-visible:outline-2 focus-visible:outline-focus"
            >
              <X aria-hidden="true" className="size-(--component-icon-sm-size)" />
            </button>
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}
