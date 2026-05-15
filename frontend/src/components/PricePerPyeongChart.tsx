import React from 'react';
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip
} from 'recharts';
import type { PricePerPyeongTrend } from '@/types/loan';

interface PricePerPyeongChartProps {
  data: PricePerPyeongTrend | null | undefined;
}

export default function PricePerPyeongChart({ data }: PricePerPyeongChartProps) {
  if (!data) return null;

  // 오토 스케일: 데이터 최소/최대에서 ±5% 마진
  const allValues = data.data.flatMap((d) => [d.complex, d.dong, d.sigungu]);
  const dataMin = Math.min(...allValues);
  const dataMax = Math.max(...allValues);
  const margin = Math.max(Math.round((dataMax - dataMin) * 0.15), 50);
  const yMin = Math.max(0, Math.floor((dataMin - margin) / 100) * 100);
  const yMax = Math.ceil((dataMax + margin) / 100) * 100;

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="chart-tooltip">
          <p className="tooltip-label">{label}</p>
          {payload.map((entry: any, idx: number) => (
            <p key={idx} className="tooltip-value" style={{ color: entry.color }}>
              {entry.name}: {entry.value.toLocaleString()}만원/평
            </p>
          ))}
        </div>
      );
    }
    return null;
  };

  return (
    <div className="info-card">
      <h3>단지 평단가 vs 동/구 평균 추이</h3>
      <div style={{ fontSize: 11, color: '#6B7785', marginBottom: 8 }}>
        같은 평형 대역(전용면적 ±5㎡) 실거래만 집계한 월평균 평단가입니다. 그 달 거래 0건이면 직전 값 유지.
      </div>
      <div className="pyeong-chart-labels" style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <span className="pyeong-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#7DCCE5' }} />
          {data.complex_name} 평단가
        </span>
        <span className="pyeong-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#006FBD' }} />
          {data.dong_name} 평균
        </span>
        <span className="pyeong-label" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#051C48' }} />
          {data.sigungu_name} 평균
        </span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data.data} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
          <XAxis dataKey="date" tick={{ fontSize: 12 }} />
          <YAxis
            domain={[yMin, yMax]}
            tickFormatter={(v: number) => `${v.toLocaleString()}`}
            tick={{ fontSize: 11 }}
            width={70}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="complex"
            stroke="#7DCCE5"
            strokeWidth={2.5}
            dot={{ r: 4, fill: '#7DCCE5' }}
            name={`${data.complex_name} 평단가`}
          />
          <Line
            type="monotone"
            dataKey="dong"
            stroke="#006FBD"
            strokeWidth={2}
            dot={{ r: 4, fill: '#006FBD' }}
            name={`${data.dong_name} 평균`}
          />
          <Line
            type="monotone"
            dataKey="sigungu"
            stroke="#051C48"
            strokeWidth={2}
            dot={{ r: 4, fill: '#051C48' }}
            name={`${data.sigungu_name} 평균`}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
