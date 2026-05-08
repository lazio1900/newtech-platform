import React from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  Area,
  ComposedChart,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import type { CreditDataWithHistory } from '@/types/loan';

interface PriceChartsProps {
  data: CreditDataWithHistory | null | undefined;
  loanDuration?: number;
}

interface ChartDataPoint {
  date: string;
  dateLabel: string;
  ts: number;
  price: number;
}

interface JbDataPoint {
  date: string;
  dateLabel: string;
  jbPrice?: number;
  predictedPrice?: number;
  type: string;
}

export default function PriceCharts({ data, loanDuration = 12 }: PriceChartsProps) {
  if (!data) return null;

  const formatPrice = (value: number): string => {
    return `${(value / 100000000).toFixed(1)}억`;
  };

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  const formatYearMonth = (dateStr: string): string => {
    const date = new Date(dateStr);
    return `${date.getFullYear()}.${String(date.getMonth() + 1).padStart(2, '0')}`;
  };

  // 3개월 윈도우 (오늘 기준) — X축 도메인은 데이터 유무와 무관하게 항상 [start, today]
  const _today = new Date();
  _today.setHours(23, 59, 59, 0);
  const _threeMonthsAgo = new Date(_today);
  _threeMonthsAgo.setMonth(_threeMonthsAgo.getMonth() - 3);
  _threeMonthsAgo.setHours(0, 0, 0, 0);
  const startTs = _threeMonthsAgo.getTime();
  const endTs = _today.getTime();
  const _inWindow = (d: string) => {
    const t = new Date(d).getTime();
    return t >= startTs && t <= endTs;
  };
  const _toPoint = (p: { date: string; price: number }) => ({
    date: p.date,
    dateLabel: formatDate(p.date),
    ts: new Date(p.date).getTime(),
    price: p.price,
  });
  // X축 tick: 매월 1일
  const monthlyTicks: number[] = [];
  {
    const t = new Date(_threeMonthsAgo);
    t.setDate(1);
    while (t.getTime() <= endTs) {
      if (t.getTime() >= startTs) monthlyTicks.push(t.getTime());
      t.setMonth(t.getMonth() + 1);
    }
    if (!monthlyTicks.includes(endTs)) monthlyTicks.push(endTs);
  }
  const xTickFormatter = (ts: number) => {
    const d = new Date(ts);
    return `${d.getMonth() + 1}/${d.getDate()}`;
  };

  const kbData: ChartDataPoint[] = data.kb_price.history.filter(p => _inWindow(p.date)).map(_toPoint);
  const molitData: ChartDataPoint[] = data.molit_transactions.history.filter(p => _inWindow(p.date)).map(_toPoint);
  const naverData: ChartDataPoint[] = data.naver_listings.history.filter(p => _inWindow(p.date)).map(_toPoint);

  // JB 적정시세 추이 — backend 산출. 시점이 1개라도 표시.
  const jbHistorySrc = data.jb_detail?.history || [];
  const jbHistoryData = (
    jbHistorySrc.length > 0
      ? jbHistorySrc
      : (data.jb_fair_price ? [{ date: new Date().toISOString().split('T')[0], price: data.jb_fair_price }] : [])
  ).filter(p => _inWindow(p.date)).map(_toPoint);
  const latestJbPrice = data.jb_fair_price || jbHistoryData[jbHistoryData.length - 1]?.price || 0;
  const jbWeights = data.jb_detail?.weights || { kb: 0.3, molit: 0.6, naver: 0.1 };

  // JB 차트 데이터 — 실측(history) + 예측(forecast 향후 3개월만). 6개월 윈도우.
  const forecastSrc = (data.jb_detail?.forecast || []).slice(0, 4);  // m=0..3
  const jbCombined: Array<{
    ts: number;
    date: string;
    history?: number;
    predicted?: number;
    lower?: number;
    upper?: number;
    range?: [number, number];
  }> = [];
  for (const h of jbHistoryData) {
    jbCombined.push({ ts: h.ts, date: h.date, history: h.price });
  }
  for (const f of forecastSrc) {
    const ts = new Date(f.date).getTime();
    jbCombined.push({
      ts,
      date: f.date,
      predicted: f.predicted,
      lower: f.lower,
      upper: f.upper,
      range: [f.lower, f.upper],
    });
  }
  jbCombined.sort((a, b) => a.ts - b.ts);

  // JB 차트 X축 — 과거 3개월 ~ 미래 3개월 (총 6개월)
  const jbEndDate = new Date(_today);
  jbEndDate.setMonth(jbEndDate.getMonth() + 3);
  const jbEndTs = jbEndDate.getTime();
  const jbXTicks: number[] = [];
  {
    const t = new Date(_threeMonthsAgo);
    t.setDate(1);
    while (t.getTime() <= jbEndTs) {
      if (t.getTime() >= startTs) jbXTicks.push(t.getTime());
      t.setMonth(t.getMonth() + 1);
    }
    if (!jbXTicks.includes(endTs)) jbXTicks.push(endTs);
  }

  // 3개 차트 공통 Y축 범위 (KB, 실거래가, 매매호가) — 데이터 없을 때 가드
  const allPrices = [
    ...kbData.map(d => d.price),
    ...molitData.map(d => d.price),
    ...naverData.map(d => d.price),
  ].filter(v => v > 0);
  const priceMin = allPrices.length > 0 ? Math.min(...allPrices) : 0;
  const priceMax = allPrices.length > 0 ? Math.max(...allPrices) : 100000000;
  const priceMargin = Math.max(Math.round((priceMax - priceMin) * 0.15), 50000000);
  const sharedYMin = Math.max(0, Math.floor((priceMin - priceMargin) / 100000000) * 100000000);
  const sharedYMax = Math.ceil((priceMax + priceMargin) / 100000000) * 100000000;

  // JB 차트 Y축 — 실측 + 예측 신뢰구간 모두 포함
  const jbAllValues: number[] = [];
  for (const c of jbCombined) {
    if (c.history) jbAllValues.push(c.history);
    if (c.lower) jbAllValues.push(c.lower);
    if (c.upper) jbAllValues.push(c.upper);
  }
  const jbMin = jbAllValues.length > 0 ? Math.min(...jbAllValues) : sharedYMin;
  const jbMax = jbAllValues.length > 0 ? Math.max(...jbAllValues) : sharedYMax;
  const jbMargin = Math.max(Math.round((jbMax - jbMin) * 0.10), 30000000);
  const jbYMin = Math.max(0, Math.floor((jbMin - jbMargin) / 100000000) * 100000000);
  const jbYMax = Math.ceil((jbMax + jbMargin) / 100000000) * 100000000;


  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const dataPoint = payload[0].payload;
      return (
        <div className="chart-tooltip">
          <p className="tooltip-label">{dataPoint.date}</p>
          <p className="tooltip-value">{formatPrice(dataPoint.price)}</p>
        </div>
      );
    }
    return null;
  };

  return (
    <>
      <div className="price-charts-grid">
        <div className="chart-box">
          <h4>KB 시세 추이</h4>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={kbData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
              <XAxis
                dataKey="ts"
                type="number"
                domain={[startTs, endTs]}
                ticks={monthlyTicks}
                tickFormatter={xTickFormatter}
                tick={{ fontSize: 10 }}
                allowDataOverflow
              />
              <YAxis
                domain={[sharedYMin, sharedYMax]}
                tickFormatter={formatPrice}
                tick={{ fontSize: 10 }}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#006FBD"
                strokeWidth={2}
                dot={{ r: 3, fill: '#006FBD' }}
                name="KB시세"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-box">
          <h4>실거래가 추이</h4>
          <ResponsiveContainer width="100%" height={200}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
              <XAxis
                dataKey="ts"
                type="number"
                domain={[startTs, endTs]}
                ticks={monthlyTicks}
                tickFormatter={xTickFormatter}
                tick={{ fontSize: 10 }}
                allowDataOverflow
              />
              <YAxis
                dataKey="price"
                domain={[sharedYMin, sharedYMax]}
                tickFormatter={formatPrice}
                tick={{ fontSize: 10 }}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Scatter
                data={molitData}
                fill="#7DCCE5"
                name="실거래가"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-box">
          <h4>부동산 매매호가 추이</h4>
          <ResponsiveContainer width="100%" height={200}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
              <XAxis
                dataKey="ts"
                type="number"
                domain={[startTs, endTs]}
                ticks={monthlyTicks}
                tickFormatter={xTickFormatter}
                tick={{ fontSize: 10 }}
                allowDataOverflow
              />
              <YAxis
                dataKey="price"
                domain={[sharedYMin, sharedYMax]}
                tickFormatter={formatPrice}
                tick={{ fontSize: 10 }}
                width={60}
              />
              <Tooltip content={<CustomTooltip />} />
              <Scatter
                data={naverData}
                fill="#051C48"
                name="매매호가"
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* JB 적정시세 추이 + 향후 3개월 예측 (1단계: 동적 가중치 + IQR + 90% 신뢰구간) */}
      <div className="chart-box jb-fair-price-chart">
        <div className="jb-chart-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <h4>JB 적정 시세 추이 · 3개월 예측</h4>
          <div style={{ fontSize: 11, color: '#666' }}>
            <span style={{ marginRight: 12 }}>KB <strong style={{ color: '#006FBD' }}>{Math.round((jbWeights.kb || 0) * 100)}%</strong></span>
            <span style={{ marginRight: 12 }}>실거래 <strong style={{ color: '#7DCCE5' }}>{Math.round((jbWeights.molit || 0) * 100)}%</strong></span>
            <span style={{ marginRight: 12 }}>호가 <strong style={{ color: '#051C48' }}>{Math.round((jbWeights.naver || 0) * 100)}%</strong></span>
            <span>현재 <strong style={{ color: '#FF8C00' }}>{formatPrice(latestJbPrice)}</strong></span>
          </div>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={jbCombined}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E0E0E0" />
            <XAxis
              dataKey="ts"
              type="number"
              domain={[startTs, jbEndTs]}
              ticks={jbXTicks}
              tickFormatter={xTickFormatter}
              tick={{ fontSize: 10 }}
              allowDataOverflow
            />
            <YAxis
              domain={[jbYMin, jbYMax]}
              tickFormatter={formatPrice}
              tick={{ fontSize: 10 }}
              width={65}
            />
            <Tooltip
              content={({ active, payload }: any) => {
                if (!active || !payload || !payload.length) return null;
                const p = payload[0].payload;
                return (
                  <div className="chart-tooltip">
                    <p className="tooltip-label">{p.date}</p>
                    {p.history && <p className="tooltip-value" style={{ color: '#FF8C00' }}>실측 JB: {formatPrice(p.history)}</p>}
                    {p.predicted && <p className="tooltip-value" style={{ color: '#FF8C00' }}>예측: {formatPrice(p.predicted)}</p>}
                    {p.lower && p.upper && (
                      <p className="tooltip-value" style={{ color: '#888', fontSize: 11 }}>
                        90% CI: {formatPrice(p.lower)} ~ {formatPrice(p.upper)}
                      </p>
                    )}
                  </div>
                );
              }}
            />
            <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 11, paddingBottom: 4 }} />
            {/* 신뢰구간 Area (반투명) */}
            <Area
              type="monotone"
              dataKey="range"
              stroke="none"
              fill="#FF8C00"
              fillOpacity={0.15}
              name="90% 신뢰구간"
              connectNulls={false}
              isAnimationActive={false}
            />
            {/* 실측 라인 */}
            <Line
              type="monotone"
              dataKey="history"
              stroke="#FF8C00"
              strokeWidth={2.5}
              dot={{ r: 4, fill: '#FF8C00' }}
              name="실측"
              connectNulls={false}
              isAnimationActive={false}
            />
            {/* 예측 라인 (점선) */}
            <Line
              type="monotone"
              dataKey="predicted"
              stroke="#FF8C00"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3, fill: '#FFF', stroke: '#FF8C00', strokeWidth: 2 }}
              name="예측"
              connectNulls={false}
              isAnimationActive={false}
            />
            {/* 오늘 기준선 */}
            <ReferenceLine x={endTs} stroke="#999" strokeDasharray="3 3" label={{ value: '오늘', fill: '#666', fontSize: 10, position: 'top' }} />
          </ComposedChart>
        </ResponsiveContainer>
        {data.jb_detail?.notes && data.jb_detail.notes.length > 0 && (
          <div style={{ fontSize: 10, color: '#888', marginTop: 6 }}>
            {data.jb_detail.notes.join(' · ')}
          </div>
        )}
      </div>
    </>
  );
}
