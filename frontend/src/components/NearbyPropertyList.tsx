import type { NearbyPropertyTrends } from '@/types/loan';

interface NearbyPropertyListProps {
  data: NearbyPropertyTrends | null | undefined;
}

export default function NearbyPropertyList({ data }: NearbyPropertyListProps) {
  if (!data || data.similar_properties.length === 0) return null;

  const formatPrice = (value: number): string => {
    const eok = value / 100000000;
    if (eok >= 1) {
      return eok % 1 === 0 ? `${eok.toFixed(0)}억` : `${eok.toFixed(1)}억`;
    }
    return `${(value / 10000).toLocaleString()}만`;
  };

  const fmtDist = (m: number | null | undefined) =>
    m == null ? '-' : m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`;

  const colorOfDiff = (pct: number | null | undefined) => {
    if (pct == null) return '#666';
    if (pct > 0) return '#EF5350';
    if (pct < 0) return '#3498DB';
    return '#666';
  };

  return (
    <div className="info-card">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <h3 style={{ margin: 0 }}>인근 유사 물건지 목록</h3>
        <div style={{ fontSize: 11, color: '#666' }}>
          {data.radius_m != null && <span style={{ marginRight: 12 }}>반경 {fmtDist(data.radius_m)}</span>}
          {data.avg_change_rate != null && (
            <span style={{ marginRight: 12 }}>
              인근 평균 변동{' '}
              <strong style={{ color: data.avg_change_rate >= 0 ? '#EF5350' : '#3498DB' }}>
                {data.avg_change_rate >= 0 ? '+' : ''}{(data.avg_change_rate * 100).toFixed(1)}%
              </strong>
            </span>
          )}
          {data.target_recent_price != null && (
            <span>기준가 <strong>{formatPrice(data.target_recent_price)}</strong></span>
          )}
        </div>
      </div>
      <div className="info-content">
        <table className="rights-table">
          <thead>
            <tr>
              <th>단지명</th>
              <th>거리</th>
              <th>평형</th>
              <th>년식</th>
              <th>세대수</th>
              <th>최근가</th>
              <th>기준 대비</th>
              <th>3개월 변동</th>
              <th>유사도</th>
            </tr>
          </thead>
          <tbody>
            {data.similar_properties.map((prop, idx) => (
              <tr key={idx}>
                <td>
                  <div style={{ fontWeight: 600 }}>{prop.name}</div>
                  <div style={{ fontSize: 10, color: '#888' }}>{prop.sigungu}</div>
                </td>
                <td className="center">{fmtDist(prop.distance_m)}</td>
                <td className="center">
                  {prop.area}평
                  {prop.exclusive_m2 ? <div style={{ fontSize: 10, color: '#888' }}>{prop.exclusive_m2.toFixed(1)}㎡</div> : null}
                </td>
                <td className="center">{prop.age}년</td>
                <td className="center">{prop.units.toLocaleString()}</td>
                <td className="center">{formatPrice(prop.recent_price)}</td>
                <td className="center" style={{ color: colorOfDiff(prop.price_diff_pct), fontWeight: 600 }}>
                  {prop.price_diff_pct == null ? '-' : `${prop.price_diff_pct >= 0 ? '+' : ''}${prop.price_diff_pct.toFixed(1)}%`}
                </td>
                <td className="center" style={{ color: prop.price_change_rate >= 0 ? '#EF5350' : '#3498DB', fontWeight: 600 }}>
                  {prop.price_change_rate >= 0 ? '+' : ''}{(prop.price_change_rate * 100).toFixed(1)}%
                </td>
                <td className="center">
                  {prop.similarity != null ? (
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      <div style={{ width: 36, height: 4, background: '#eee', borderRadius: 2, overflow: 'hidden' }}>
                        <div style={{ width: `${prop.similarity * 100}%`, height: '100%', background: '#FF8C00' }} />
                      </div>
                      <span style={{ fontSize: 10, color: '#666' }}>{(prop.similarity * 100).toFixed(0)}</span>
                    </div>
                  ) : '-'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
