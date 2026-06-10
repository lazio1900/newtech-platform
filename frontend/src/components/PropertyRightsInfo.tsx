import type { CSSProperties, ReactNode } from 'react';
import type { PropertyRightsData } from '@/types/loan';

interface PropertyRightsInfoProps {
  data: PropertyRightsData | null | undefined;
  onViewPDF: () => void;
}

interface Col<T> {
  label: string;
  value: (e: T) => ReactNode;
  tdClass?: string;
  tdStyle?: CSSProperties;
}

// 값이 한 행도 없는(전부 빈) 컬럼은 숨긴다 — 예: 내부망에서 (주민)등록번호 미제공
function RightsTable<T>({ rows, cols }: { rows: T[]; cols: Col<T>[] }) {
  const hasValue = (c: Col<T>, e: T): boolean => {
    const v = c.value(e);
    return !(v === null || v === undefined || (typeof v === 'string' && v.trim() === ''));
  };
  const visible = cols.filter((c) => rows.some((r) => hasValue(c, r)));
  return (
    <table className="rights-table">
      <thead>
        <tr>{visible.map((c) => <th key={c.label}>{c.label}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((r, idx) => (
          <tr key={idx}>
            {visible.map((c) => (
              <td key={c.label} className={c.tdClass} style={c.tdStyle}>{c.value(r)}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function PropertyRightsInfo({ data, onViewPDF }: PropertyRightsInfoProps) {
  if (!data) return null;

  return (
    <div className="info-card rights-highlight">
      <div className="card-header">
        <h3>담보 물건 권리 정보 조회 영역</h3>
        <button className="pdf-view-btn" onClick={onViewPDF}>
          등기부등본 원본 보기
        </button>
      </div>

      <div className="info-content">
        <div className="rights-section">
          <h4 className="rights-section-title">1. 소유지분현황 (갑구)</h4>
          {data.ownership_entries.length > 0 ? (
            <RightsTable
              rows={data.ownership_entries}
              cols={[
                { label: '등기명의인', value: (e) => e.name },
                { label: '(주민)등록번호', value: (e) => e.reg_number },
                { label: '최종지분', value: (e) => e.share },
                { label: '주소', value: (e) => e.address },
                { label: '순위번호', value: (e) => e.rank_number, tdClass: 'center' },
              ]}
            />
          ) : (
            <p className="rights-empty">기록사항 없음</p>
          )}
        </div>

        <div className="rights-section">
          <h4 className="rights-section-title">2. 소유지분을 제외한 소유권에 관한 사항 (갑구)</h4>
          {data.ownership_other_entries.length > 0 ? (
            <RightsTable
              rows={data.ownership_other_entries}
              cols={[
                { label: '순위번호', value: (e) => e.rank_number, tdClass: 'center' },
                { label: '등기목적', value: (e) => e.purpose },
                { label: '접수정보', value: (e) => e.receipt_info, tdClass: 'nowrap' },
                { label: '주요등기사항', value: (e) => e.details, tdStyle: { whiteSpace: 'pre-line' } },
              ]}
            />
          ) : (
            <p className="rights-empty">- 기록사항 없음</p>
          )}
        </div>

        <div className="rights-section">
          <h4 className="rights-section-title">3. (근)저당권 및 전세권 등 (을구)</h4>
          {data.mortgage_entries.length > 0 ? (
            <RightsTable
              rows={data.mortgage_entries}
              cols={[
                { label: '순위번호', value: (e) => e.rank_number, tdClass: 'center' },
                { label: '등기목적', value: (e) => e.purpose },
                { label: '접수정보', value: (e) => e.receipt_info, tdClass: 'nowrap', tdStyle: { whiteSpace: 'pre-line' } },
                { label: '주요등기사항', value: (e) => e.main_details, tdStyle: { whiteSpace: 'pre-line' } },
                { label: '대상소유자', value: (e) => e.target_owner },
              ]}
            />
          ) : (
            <p className="rights-empty">- 기록사항 없음</p>
          )}
        </div>
      </div>
    </div>
  );
}
