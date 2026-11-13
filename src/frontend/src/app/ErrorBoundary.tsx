import { Component, type ErrorInfo, type ReactNode } from "react";
import { useLocation } from "react-router";
import { I18nProvider } from "../i18n";
import { frontendLog } from "../shared/logging";
import { AppErrorPage } from "./AppErrorPage";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Changing this key clears a caught error (e.g. on route change). */
  resetKey?: string;
}

interface ErrorBoundaryState {
  hasError: boolean;
  prevResetKey?: string;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  static getDerivedStateFromProps(
    props: ErrorBoundaryProps,
    state: ErrorBoundaryState,
  ): Partial<ErrorBoundaryState> | null {
    if (props.resetKey !== state.prevResetKey) {
      return { hasError: false, prevResetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // t058 A27: record the render error on the frontend log channel —
    // never silently drop it, never print it as console debug output.
    frontendLog.logError(error, {
      source: "ErrorBoundary",
      componentStack: info.componentStack,
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <I18nProvider>
          <AppErrorPage />
        </I18nProvider>
      );
    }
    return this.props.children;
  }
}

/**
 * Route-level boundary: lives inside the Router, so a render error in
 * one route shows the error page for that route only, and navigating to
 * another route (a new location.key) resets it. The root boundary in
 * main.tsx stays as the last-resort fallback.
 */
export function RouteErrorBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary resetKey={location.key}>{children}</ErrorBoundary>;
}
