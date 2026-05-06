import type { PropertyBasicData } from '@/types/loan';

interface PropertyBasicInfoProps {
  data: PropertyBasicData | null | undefined;
}

export default function PropertyBasicInfo({ data }: PropertyBasicInfoProps) {
  if (!data) return null;

  return (
    <div className="info-card">
      <h3>담보 물건 기초 정보 조회 영역</h3>
      <div className="info-content">
        {data.complex_name && (
          <div className="info-row">
            <span className="label">단지명:</span>
            <span className="value"><strong>{data.complex_name}</strong></span>
          </div>
        )}
        <div className="info-row">
          <span className="label">주소:</span>
          <span className="value">{data.address}</span>
        </div>
        <div className="info-row">
          <span className="label">세대수:</span>
          <span className="value">{data.units != null ? `${data.units.toLocaleString()}세대` : "N/A"}</span>
        </div>
        <div className="info-row">
          <span className="label">연식:</span>
          <span className="value">{data.age != null ? `약 ${data.age}년` : "N/A"}</span>
        </div>
        <div className="info-row">
          <span className="label">전용면적:</span>
          <span className="value">{data.area != null ? `${data.area}평` : "N/A"}</span>
        </div>
        <div className="info-row">
          <span className="label">입지점수:</span>
          <span className="value">{data.location_score != null ? `${data.location_score}/100` : "N/A"}</span>
        </div>
      </div>
    </div>
  );
}
