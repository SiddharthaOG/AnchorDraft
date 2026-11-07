/** Loading screen component. */

interface LoadingScreenProps {
  message?: string;
  fullScreen?: boolean;
}

export function LoadingScreen({ message = 'Loading...', fullScreen = true }: LoadingScreenProps) {
  const baseStyles = fullScreen
    ? 'fixed inset-0 z-50 bg-white flex items-center justify-center'
    : 'flex items-center justify-center py-12';

  return (
    <div className={baseStyles} role="status" aria-live="polite" aria-label={message}>
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
        <p className="text-gray-600">{message}</p>
      </div>
    </div>
  );
}

export default LoadingScreen;