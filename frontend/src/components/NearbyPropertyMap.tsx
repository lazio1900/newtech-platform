import L from 'leaflet';
import { MapContainer, TileLayer, CircleMarker, Marker, Tooltip } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import type { NearbyPropertyTrends } from '@/types/loan';

// 번호 마커 — 표 번호와 일치
const numberedIcon = (n: number) =>
  L.divIcon({
    className: 'nearby-numbered-marker',
    html: `<div style="
      width:28px;height:28px;border-radius:50%;
      background:#006FBD;color:#fff;
      display:flex;align-items:center;justify-content:center;
      font-size:12px;font-weight:700;
      border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,0.4);
    ">${n}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  });

interface NearbyPropertyMapProps {
  data: NearbyPropertyTrends | null | undefined;
  targetAddress: string;
}

export default function NearbyPropertyMap({ data, targetAddress }: NearbyPropertyMapProps) {
  if (!data || data.similar_properties.length === 0) {
    return (
      <div className="info-card">
        <h3>인근 유사 물건지 동향</h3>
        <div style={{ padding: '40px 16px', textAlign: 'center', color: '#888', fontSize: 13 }}>
          해당 지역의 유사 단지 수집 데이터가 없습니다.
        </div>
      </div>
    );
  }

  const formatPrice = (value: number): string => `${(value / 100000000).toFixed(1)}억`;
  const formatRate = (rate: number): string => {
    const pct = (rate * 100).toFixed(1);
    return rate >= 0 ? `+${pct}%` : `${pct}%`;
  };

  const center: [number, number] = [data.target_lat, data.target_lng];

  // 폐쇄망 빌드 시 VITE_MAP_TILE_URL 을 빈 값으로 두면 외부 타일 호출 안 함 (점만 렌더).
  // 운영망: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png' 같은 URL 지정.
  const tileUrl = import.meta.env.VITE_MAP_TILE_URL || '';
  const tileAttribution = import.meta.env.VITE_MAP_TILE_ATTRIBUTION || '';

  return (
    <div className="info-card">
      <h3>인근 유사 물건지 동향</h3>
      <div className="nearby-map-container" style={{
        height: '360px', borderRadius: '8px', overflow: 'hidden',
        background: tileUrl ? undefined : '#F3F4F6',
      }}>
        <MapContainer center={center} zoom={14} style={{ height: '100%', width: '100%' }} scrollWheelZoom={false}>
          {tileUrl && (
            <TileLayer attribution={tileAttribution} url={tileUrl} />
          )}
          {/* 대상 물건 - 빨간 점 */}
          <CircleMarker
            center={center}
            radius={10}
            pathOptions={{ color: '#EF5350', fillColor: '#EF5350', fillOpacity: 0.85, weight: 2 }}
          >
            <Tooltip direction="top">
              <div style={{ fontSize: '12px', lineHeight: 1.6 }}>
                <strong>대상 물건</strong><br/>
                {targetAddress}
              </div>
            </Tooltip>
          </CircleMarker>
          {/* 유사 물건 - 번호 마커 (표와 매칭) */}
          {data.similar_properties.map((prop, idx) => (
            <Marker
              key={idx}
              position={[prop.lat, prop.lng]}
              icon={numberedIcon(idx + 1)}
            >
              <Tooltip direction="top">
                <div style={{ fontSize: '12px', lineHeight: 1.6, minWidth: '160px' }}>
                  <strong>#{idx + 1} {prop.name}</strong><br/>
                  {prop.units}세대 / {prop.age}년 / {prop.area}평<br/>
                  최근가: {formatPrice(prop.recent_price)}<br/>
                  3개월 변동:{' '}
                  <span style={{ color: prop.price_change_rate >= 0 ? '#E74C3C' : '#3498DB', fontWeight: 600 }}>
                    {formatRate(prop.price_change_rate)}
                  </span>
                </div>
              </Tooltip>
            </Marker>
          ))}
        </MapContainer>
      </div>
      <div className="nearby-map-legend">
        <span className="legend-item">
          <span className="legend-dot target"></span> 대상 물건
        </span>
        <span className="legend-item">
          <span className="legend-dot similar"></span> 유사 물건 ({data.similar_properties.length}건)
        </span>
      </div>
    </div>
  );
}
