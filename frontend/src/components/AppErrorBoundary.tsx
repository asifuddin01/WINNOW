import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorPage } from "@/components/layout/ErrorPage";

interface State {
  error: unknown;
}

/** Last line of defence for errors outside the router (providers, the router itself). */
export class AppErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo) {
    console.error("Unhandled application error", error, info.componentStack);
  }

  override render() {
    return this.state.error ? <ErrorPage error={this.state.error} /> : this.props.children;
  }
}
