import React from 'react';
import {
  ResponsiveContainer,
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
  low?: number;
  high?: number;
  range?: [number, number];  // KB 차트 상하한 Area 용
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartDataPoint }>;
}

interface JbTooltipPayload {
  date: string;
  history?: number;
  predicted?: number;
  lower?: number;
  upper?: number;
}

interface JbTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: JbTooltipPayload }>;
}

const JbTooltip = ({ active, payload }: JbTooltipProps) => {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label">{p.date}</p>
      {p.history != null && <p className="tooltip-value" style={{ color: '#FF8C00' }}>실측 JB: {formatPrice(p.history)}</p>}
      {p.predicted != null && <p className="tooltip-value" style={{ color: '#FF8C00' }}>예측: {formatPrice(p.predicted)}</p>}
      {p.lower != null && p.upper != null && (
        <p className="tooltip-value" style={{ color: '#888', fontSize: 11 }}>
          80% CI: {formatPrice(p.lower)} ~ {formatPrice(p.upper)}
        </p>
      )}
    </div>
  );
};

const formatPrice = (value: number): string => `${(value / 100000000).toFixed(1)}억`;

const CustomTooltip = ({ active, payload }: TooltipProps) => {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label">{p.date}</p>
      <p className="tooltip-value">{formatPrice(p.price)}</p>
      {p.low != null && p.high != null && (
        <p className="tooltip-value" style={{ color: '#888', fontSize: 11 }}>
          하한 {formatPrice(p.low)} · 상한 {formatPrice(p.high)}
        </p>
      )}
    </div>
  );
};

export default function PriceCharts({ data }: PriceChartsProps) {
  if (!data) return null;

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  };

  // 6개월 윈도우 (오늘 기준) — X축 도메인은 데이터 유무와 무관하게 항상 [start, today]
  const _today = new Date();
  _today.setHours(23, 59, 59, 0);
  const _windowStart = new Date(_today);
  _windowStart.setMonth(_windowStart.getMonth() - 6);
  _windowStart.setHours(0, 0, 0, 0);
  const startTs = _windowStart.getTime();
  const endTs = _today.getTime();
  const _inWindow = (d: string) => {
    const t = new Date(d).getTime();
    return t >= startTs && t <= endTs;
  };
  const _toPoint = (p: { date: string; price: number; low?: number | null; high?: number | null }): ChartDataPoint => {
    const point: ChartDataPoint = {
      date: p.date,
      dateLabel: formatDate(p.date),
      ts: new Date(p.date).getTime(),
      price: p.price,
    };
    if (p.low != null && p.high != null) {
      point.low = p.low;
      point.high = p.high;
      point.range = [p.low, p.high];
    }
    return point;
  };
  // X축 tick: 매월 1일
  const monthlyTicks: number[] = [];
  {
    const t = new Date(_windowStart);
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
    const t = new Date(_windowStart);
    t.setDate(1);
    while (t.getTime() <= jbEndTs) {
      if (t.getTime() >= startTs) jbXTicks.push(t.getTime());
      t.setMonth(t.getMonth() + 1);
    }
    if (!jbXTicks.includes(endTs)) jbXTicks.push(endTs);
  }

  // 3개 차트 공통 Y축 범위 (KB, 실거래가, 매매호가) — 데이터 없을 때 가드.
  // KB 상하한 표시 위해 low/high 도 포함.
  const allPrices = [
    ...kbData.map(d => d.price),
    ...kbData.flatMap(d => (d.low != null && d.high != null ? [d.low, d.high] : [])),
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


  return (
    <>
      <div className="price-charts-grid">
        <div className="chart-box">
          <h4>KB 시세 추이</h4>
          <ResponsiveContainer width="100%" height={200}>
            <ComposedChart data={kbData}>
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
              <Area
                type="monotone"
                dataKey="range"
                stroke="none"
                fill="#006FBD"
                fillOpacity={0.12}
                name="하한~상한"
                connectNulls={false}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="price"
                stroke="#006FBD"
                strokeWidth={2}
                dot={{ r: 3, fill: '#006FBD' }}
                name="KB시세"
              />
            </ComposedChart>
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

      {/* JB 적정시세 추이 + 향후 3개월 예측 (1단계: 동적 가중치 + IQR + 80% 신뢰구간) */}
      <div className="chart-box jb-fair-price-chart">
        <div className="jb-chart-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 8 }}>
          <h4>JB 적정 시세 추이 · 3개월 예측</h4>
          <div style={{ fontSize: 11, color: '#666' }}>
            <span style={{ marginRight: 8, color: '#444', fontWeight: 600 }}>수행달 가중치</span>
            <span style={{ marginRight: 12 }}>KB <strong style={{ color: '#006FBD' }}>{Math.round((jbWeights.kb || 0) * 100)}%</strong></span>
            <span style={{ marginRight: 12 }}>실거래 <strong style={{ color: '#7DCCE5' }}>{Math.round((jbWeights.molit || 0) * 100)}%</strong></span>
            <span style={{ marginRight: 12 }}>호가 <strong style={{ color: '#051C48' }}>{Math.round((jbWeights.naver || 0) * 100)}%</strong></span>
            <span>현재 <strong style={{ color: '#FF8C00' }}>{formatPrice(latestJbPrice)}</strong></span>
          </div>
        </div>
        {(() => {
          const last = forecastSrc[forecastSrc.length - 1];
          if (!last || !latestJbPrice) return null;
          const fmtSigned = (n: number) => {
            const abs = Math.abs(n);
            const eok = abs / 100000000;
            const sign = n >= 0 ? '+' : '-';
            return `${sign}${eok.toFixed(2)}억`;
          };
          const pct = (n: number) => `${n >= 0 ? '+' : ''}${(n * 100).toFixed(1)}%`;
          const dCenter = last.predicted - latestJbPrice;
          const dLower = last.lower - latestJbPrice;
          const dUpper = last.upper - latestJbPrice;
          const rCenter = dCenter / latestJbPrice;
          const color = dCenter >= 0 ? '#E74C3C' : '#3498DB';
          return (
            <div style={{
              fontSize: 11, color: '#555', marginTop: 4, marginBottom: 6,
              display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center',
            }}>
              <span>3개월 후 예상</span>
              <span>중심선 <strong style={{ color }}>{pct(rCenter)} ({fmtSigned(dCenter)})</strong></span>
              <span style={{ color: '#888' }}>
                80% 범위 <strong>{pct(dLower / latestJbPrice)} ~ {pct(dUpper / latestJbPrice)}</strong>
                <span style={{ marginLeft: 4 }}>({fmtSigned(dLower)} ~ {fmtSigned(dUpper)})</span>
              </span>
            </div>
          );
        })()}
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
            <Tooltip content={<JbTooltip />} />
            <Legend verticalAlign="top" align="right" wrapperStyle={{ fontSize: 11, paddingBottom: 4 }} />
            {/* 신뢰구간 Area (옅은 주황 fill) — legend rect */}
            <Area
              type="monotone"
              dataKey="range"
              stroke="none"
              fill="#FFD9A8"
              fillOpacity={0.6}
              name="80% 신뢰구간"
              legendType="rect"
              connectNulls={false}
              isAnimationActive={false}
            />
            {/* 실측: 오렌지 실선 + 채워진 동그라미 — legend circle */}
            <Line
              type="monotone"
              dataKey="history"
              stroke="#FF8C00"
              strokeWidth={2.5}
              dot={{ r: 4, fill: '#FF8C00', stroke: '#FF8C00' }}
              name="실측"
              legendType="circle"
              connectNulls={false}
              isAnimationActive={false}
            />
            {/* 예측: 오렌지 점선 + 빈 동그라미 — legend plainline */}
            <Line
              type="monotone"
              dataKey="predicted"
              stroke="#FF8C00"
              strokeWidth={2}
              strokeDasharray="6 4"
              dot={{ r: 3, fill: '#FFF', stroke: '#FF8C00', strokeWidth: 2 }}
              name="예측"
              legendType="plainline"
              connectNulls={false}
              isAnimationActive={false}
            />
            <ReferenceLine x={endTs} stroke="#999" strokeDasharray="3 3" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
