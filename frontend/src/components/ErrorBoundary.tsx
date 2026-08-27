import { Component, type ErrorInfo, type ReactNode } from "react";

/** A throw inside a terminal pane used to white-screen the whole app and take
 *  every other open session with it. SSH and websocket code fails for reasons
 *  outside our control — a dropped link, a malformed escape sequence — so the
 *  blast radius has to be one pane. */
export default class ErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[nterm] pane crashed:", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="pane-error">
        <div>
          <h3>This pane stopped</h3>
          <p>
            {this.props.label ? `${this.props.label} ` : ""}
            hit an error. Your other sessions are unaffected.
          </p>
          <pre>{error.message}</pre>
          <button className="primary" style={{ marginTop: 12 }} onClick={() => this.setState({ error: null })}>
            Retry
          </button>
        </div>
      </div>
    );
  }
}
