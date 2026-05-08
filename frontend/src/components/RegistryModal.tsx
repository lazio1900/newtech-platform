import { useEffect, useState } from 'react';
import apiClient from '../api/client';

interface RegistryModalProps {
  onClose: () => void;
  icId?: number | null;     // 발급 받은 등기부 ic_id. 없으면 sample 표시 (개발용)
}

export default function RegistryModal({ onClose, icId }: RegistryModalProps) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!icId) {
      setPdfUrl('/registry_sample.pdf');  // 개발용 fallback
      return;
    }
    let revoked = false;
    let createdUrl: string | null = null;
    setLoading(true);
    setError(null);
    apiClient
      .get(`/api/registry/${icId}/pdf`, { responseType: 'blob' })
      .then((res) => {
        if (revoked) return;
        const blob = new Blob([res.data], { type: 'application/pdf' });
        createdUrl = URL.createObjectURL(blob);
        setPdfUrl(createdUrl);
      })
      .catch((e) => {
        const status = e?.response?.status;
        if (status === 202) {
          setError('등기부등본이 아직 발급 처리 중입니다. 잠시 후 다시 시도해주세요.');
        } else {
          setError(
            e?.response?.data?.detail
            || e?.message
            || 'PDF 를 불러올 수 없습니다',
          );
        }
      })
      .finally(() => setLoading(false));
    return () => {
      revoked = true;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [icId]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content registry-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>등기부등본 원본 {icId ? <span style={{ fontSize: 12, color: '#888' }}>(ID: {icId})</span> : null}</h2>
          <button className="modal-close-btn" onClick={onClose}>×</button>
        </div>

        <div className="modal-body" style={{ padding: 0, flex: 1, position: 'relative' }}>
          {loading && (
            <div style={{
              position: 'absolute', inset: 0, display: 'flex',
              alignItems: 'center', justifyContent: 'center', color: '#666',
            }}>
              등기부등본을 불러오는 중...
            </div>
          )}
          {error && (
            <div style={{
              padding: 24, color: '#991B1B', background: '#FEE2E2',
              borderRadius: 4, margin: 16,
            }}>
              {error}
            </div>
          )}
          {!error && pdfUrl && (
            <iframe
              src={pdfUrl}
              title="등기부등본"
              style={{ width: '100%', height: '100%', border: 'none' }}
            />
          )}
        </div>
      </div>
    </div>
  );
}
