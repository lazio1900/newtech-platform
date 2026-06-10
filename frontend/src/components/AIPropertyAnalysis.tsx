import { useState } from 'react';
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip
} from 'recharts';
import type { ComplexScores, LocationScores } from '@/types/loan';

interface AIPropertyAnalysisProps {
  analysis: string | null | undefined;
  locationScores?: LocationScores | null;        // 외부 모드 6축
  complexScores?: ComplexScores | null;          // 내부망 모드 5축
}

interface RadarDataItem {
  axis: string;
  value: number;
  fullMark: number;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ value: number; payload: { axis: string } }>;
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (active && payload && payload.length) {
    return (
      <div style={{
        backgroundColor: 'rgba(255,255,255,0.95)',
        border: '1px solid #E0E0E0',
        borderRadius: '4px',
        padding: '8px 12px',
        boxShadow: '0 2px 8px rgba(0,0,0,0.15)'
      }}>
        <p style={{ margin: 0, fontSize: '13px', color: '#666' }}>
          {payload[0].payload.axis}
        </p>
        <p style={{ margin: '4px 0 0', fontSize: '15px', fontWeight: 700, color: '#333' }}>
          {payload[0].value}점
        </p>
      </div>
    );
  }
  return null;
}

export default function AIPropertyAnalysis({ analysis, locationScores, complexScores }: AIPropertyAnalysisProps) {
  const [showDetail, setShowDetail] = useState<boolean>(false);

  if (!analysis) return null;

  // 내부망(complexScores) 우선 — 둘 다 없으면 텍스트만.
  const radarData: RadarDataItem[] | null = complexScores ? [
    { axis: '단지 규모', value: complexScores.scale, fullMark: 100 },
    { axis: '연식', value: complexScores.age, fullMark: 100 },
    { axis: '주차 편의', value: complexScores.parking, fullMark: 100 },
    { axis: '시세 안정성', value: complexScores.price_stability, fullMark: 100 },
    { axis: '단지 위상', value: complexScores.landmark, fullMark: 100 },
  ] : locationScores ? [
    { axis: '역세권', value: locationScores.station_walk, fullMark: 100 },
    { axis: '노선 다양성', value: locationScores.commute_time, fullMark: 100 },
    { axis: '단지 규모', value: locationScores.units_score, fullMark: 100 },
    { axis: '학군', value: locationScores.school_walk, fullMark: 100 },
    { axis: '생활환경', value: locationScores.living_env, fullMark: 100 },
    { axis: '자연환경', value: locationScores.nature_env, fullMark: 100 },
  ] : null;

  const avgScore = radarData
    ? Math.round(radarData.reduce((s, d) => s + d.value, 0) / radarData.length)
    : null;

  const mixedUseBadge = complexScores
    ? (complexScores.is_mixed_use === true ? '주상복합'
      : complexScores.is_mixed_use === false ? '일반 아파트' : null)
    : null;

  const getGradeInfo = (score: number) => {
    if (score >= 90) return { grade: 'A', label: '최우수', color: '#006FBD' };
    if (score >= 80) return { grade: 'B', label: '우수', color: '#20c997' };
    if (score >= 70) return { grade: 'C', label: '양호', color: '#FFA726' };
    if (score >= 60) return { grade: 'D', label: '보통', color: '#FF7043' };
    return { grade: 'E', label: '미흡', color: '#EF5350' };
  };

  const gradeInfo = avgScore ? getGradeInfo(avgScore) : null;

  return (
    <div className="ai-card">
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <h3 style={{ margin: 0 }}>AI 입지 분석 결과</h3>
          {mixedUseBadge && (
            <span style={{
              fontSize: '11px',
              fontWeight: 600,
              padding: '2px 8px',
              borderRadius: '10px',
              color: mixedUseBadge === '주상복합' ? '#B45309' : '#374151',
              backgroundColor: mixedUseBadge === '주상복합' ? '#FEF3C7' : '#F3F4F6',
            }}>
              {mixedUseBadge}
            </span>
          )}
        </div>
        <button
          onClick={() => setShowDetail(!showDetail)}
          style={{
            padding: '6px 14px',
            backgroundColor: showDetail ? '#051C48' : '#006FBD',
            color: '#FFFFFF',
            border: 'none',
            borderRadius: '4px',
            fontSize: '12px',
            fontWeight: 500,
            cursor: 'pointer',
            fontFamily: "'Noto Sans KR', sans-serif",
            whiteSpace: 'nowrap',
            transition: 'background-color 0.2s'
          }}
        >
          {showDetail ? '차트 보기' : '상세 보기'}
        </button>
      </div>

      {showDetail ? (
        <div className="ai-content">
          <pre>{analysis}</pre>
        </div>
      ) : (
        radarData ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="72%">
                  <PolarGrid stroke="#D0D0D0" />
                  <PolarAngleAxis
                    dataKey="axis"
                    tick={{ fontSize: 11, fill: '#555' }}
                  />
                  <PolarRadiusAxis
                    angle={90}
                    domain={[0, 100]}
                    tick={{ fontSize: 10, fill: '#999' }}
                    tickCount={6}
                  />
                  <Radar
                    name="입지 점수"
                    dataKey="value"
                    stroke="#006FBD"
                    fill="#006FBD"
                    fillOpacity={0.25}
                    strokeWidth={2}
                  />
                  <Tooltip content={<CustomTooltip />} />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            <div style={{
              width: '140px',
              minWidth: '140px',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px'
            }}>
              <div style={{
                textAlign: 'center',
                padding: '14px 8px',
                backgroundColor: '#FFFFFF',
                borderRadius: '8px',
                boxShadow: '0 1px 4px rgba(0,0,0,0.08)'
              }}>
                <div style={{
                  fontSize: '32px',
                  fontWeight: 800,
                  color: gradeInfo!.color,
                  lineHeight: 1
                }}>
                  {gradeInfo!.grade}
                </div>
                <div style={{ fontSize: '12px', color: '#999', marginTop: '4px' }}>
                  {gradeInfo!.label} ({avgScore}점)
                </div>
              </div>

              {radarData.map((item) => (
                <div key={item.axis} style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  fontSize: '12px',
                  padding: '0 4px'
                }}>
                  <span style={{ color: '#666' }}>{item.axis}</span>
                  <span style={{ fontWeight: 600, color: '#333' }}>{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="ai-content">
            <pre>{analysis}</pre>
          </div>
        )
      )}
    </div>
  );
}
