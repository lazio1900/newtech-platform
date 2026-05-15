import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ErrorBoundary } from 'react-error-boundary'
import { applyInterfacePrefs } from './lib/interfacePrefs'
import ErrorFallback from './components/ErrorFallback'
import './App.css'
import App from './App'

// 사용자 화면 인터페이스 선호도 (글자 크기·표 밀도) 를 document root 에 반영.
applyInterfacePrefs();

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
