import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Log diagnostic metadata only; never log props, state, or rendered draft content.
    console.error('Application render failed', {
      errorType: error.name || 'Error',
      message: error.message,
      componentStack: info.componentStack,
    });
  }

  private recover = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <main className="anchordraft-error-screen" role="alert">
          <div className="anchordraft-error-mark" aria-hidden="true">!</div>
          <p className="anchordraft-eyebrow">ANCHORDRAFT / RECOVERY</p>
          <h1>Something interrupted this workspace.</h1>
          <p>Something went wrong while rendering this page. If you had unsaved edits, they may not have been saved. Reload the application to try again.</p>
          <button type="button" onClick={this.recover}>Reload workspace <span aria-hidden="true">↗</span></button>
        </main>
      );
    }

    return this.props.children;
  }
}
