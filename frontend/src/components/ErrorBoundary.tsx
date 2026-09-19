/**
 * Last-resort boundary so one bad render shows a message instead of a blank
 * page. Without it a throw anywhere in the tree unmounts everything, which is
 * indistinguishable from the app failing to load at all.
 */
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the stack in the console for anyone with devtools open.
    console.error("Unhandled render error", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <main className="page page--narrow">
        <div className="card stack">
          <h1>Something broke on this page</h1>
          <p className="muted">
            This is a bug on our side, not something you did. Reloading usually helps.
          </p>
          <pre
            className="tiny"
            style={{
              whiteSpace: "pre-wrap",
              overflowX: "auto",
              background: "var(--surface-sunken)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
              padding: "0.75rem",
              margin: 0,
            }}
          >
            {error.message}
          </pre>
          <div className="row">
            <button type="button" className="btn" onClick={() => window.location.reload()}>
              Reload
            </button>
            <a className="btn btn--secondary" href="/">
              Go home
            </a>
          </div>
        </div>
      </main>
    );
  }
}
