import { Component, type ReactNode } from "react";
import { I18nProvider } from "../i18n";
import { AppErrorPage } from "./AppErrorPage";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
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
