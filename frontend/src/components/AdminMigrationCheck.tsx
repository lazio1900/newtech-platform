import { useCallback, useEffect, useState } from 'react';
import { adminMigrationApi, type ChecklistResponse } from '../api/adminMigration';

interface Props {
  /** 미충족 항목의 deep-link 클릭 시 관리자 패널의 다른 서브탭으로 이동 */
  onNavigate?: (subTab: 'db' | 'data-mappings') => void;
}

export default function AdminMigrationCheck({ onNavigate }: Props) {
  const [data, setData] = useState<ChecklistResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await adminMigrationApi.checklist();
      setData(r);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '체크리스트 조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleLink = (link: string | null) => {
    if (!link || !onNavigate) return;
    if (link.includes('db-connections')) onNavigate('db');
    else if (link.includes('data-mappings')) onNavigate('data-mappings');
  };

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: '#051C48' }}>운영 전환 체크리스트</h2>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          style={{ padding: '6px 14px', background: '#fff', color: '#374151', border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 13, cursor: 'pointer' }}
        >
          {loading ? '확인 중…' : '새로고침'}
        </button>
      </div>

      <p style={{ color: '#6B7280', fontSize: 13, margin: '0 0 16px 0' }}>
        사내망 Oracle 전환 전 사전 조건을 자동 검증합니다. 미충족 항목은 옆의 링크로 이동해 해결하세요.
      </p>

      {error && (
        <div style={{ background: '#FEE2E2', color: '#991B1B', padding: 10, borderRadius: 4, marginBottom: 12 }}>
          {error}
        </div>
      )}

      {data && (
        <div style={{
          background: data.all_ok ? '#ECFDF5' : '#FFFBEB',
          border: `1px solid ${data.all_ok ? '#20c997' : '#F59E0B'}`,
          color: data.all_ok ? '#065F46' : '#92400E',
          padding: 12, borderRadius: 8, marginBottom: 16, fontWeight: 600,
        }}>
          {data.all_ok ? '✓ 모든 항목 통과 — 운영 전환 가능' : '⚠ 일부 항목 미충족 — 아래 항목을 해결하세요'}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {data?.items.map((it) => (
          <div
            key={it.key}
            style={{
              border: '1px solid #E5E7EB', borderRadius: 8, padding: 14,
              display: 'flex', alignItems: 'center', gap: 12, background: '#fff',
            }}
          >
            <span style={{
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              width: 28, height: 28, borderRadius: '50%',
              background: it.ok ? '#20c997' : '#EF5350', color: '#fff', fontWeight: 700,
            }}>
              {it.ok ? '✓' : '✕'}
            </span>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, color: '#051C48' }}>{it.label}</div>
              <div style={{ fontSize: 13, color: '#6B7280', marginTop: 2 }}>{it.detail}</div>
            </div>
            {it.link && !it.ok && (
              <button
                type="button"
                onClick={() => handleLink(it.link)}
                style={{ padding: '6px 12px', background: '#006FBD', color: '#fff', border: 'none', borderRadius: 4, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}
              >
                바로가기
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
