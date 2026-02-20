import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'
import './App.css'
import App from './App'

function ErrorFallback({ error, resetErrorBoundary }: { error: Error; resetErrorBoundary: () => void }) {
  return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <h2>오류가 발생했습니다</h2>
      <p style={{ color: '#666' }}>{error.message}</p>
      <button onClick={resetErrorBoundary} style={{ marginTop: 16, padding: '8px 24px', cursor: 'pointer' }}>
        다시 시도
      </button>
    </div>
  )
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000,
      retry: 1,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <ErrorBoundary FallbackComponent={ErrorFallback}>
      <App />
    </ErrorBoundary>
  </QueryClientProvider>
)
