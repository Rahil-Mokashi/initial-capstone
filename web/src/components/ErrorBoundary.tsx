import { RefreshCw } from 'lucide-react';
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { Button } from './ui/Button';

interface Props {
  children: ReactNode;
}

/** A bug in one screen shows a recoverable message instead of a blank window. */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div
        role="alert"
        className="mx-auto flex max-w-md flex-col items-center gap-4 p-10 text-center"
      >
        <h2 className="text-xl font-bold">Something went wrong on this screen</h2>
        <p className="text-sm text-muted">
          Your data is safe. Reload the screen; if it happens again, tell your administrator what
          you were doing.
        </p>
        <Button variant="primary" onClick={() => this.setState({ failed: false })}>
          <RefreshCw className="size-4" aria-hidden /> Reload this screen
        </Button>
      </div>
    );
  }
}
