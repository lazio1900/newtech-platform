/**
 * Top-level ErrorBoundary fallback UI.
 * main.tsx 에서 ErrorBoundary 의 FallbackComponent 로 사용.
 */
export default function ErrorFallback({ error, resetErrorBoundary }: { error: Error; resetErrorBoundary: () => void }) {
  return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <h2>오류가 발생했습니다</h2>
      <p style={{ color: '#666' }}>{error.message}</p>
      <button onClick={resetErrorBoundary} style={{ marginTop: 16, padding: '8px 24px', cursor: 'pointer' }}>
        다시 시도
      </button>
    </div>
  );
}
