import type { JBFairPriceDetail } from '../types/loan';

interface AIMarketAnalysisProps {
  analysis: string | null | undefined;
  jbDetail?: JBFairPriceDetail | null;
}

const SOURCE_LABEL: Record<string, string> = {
  kb: 'KB 추정가',
  molit: '실거래(국토부)',
  naver: '호가(KB 매물)',
};

function formatEok(won: number | null | undefined): string {
  if (!won) return '-';
  return `${(won / 1e8).toFixed(2)}억`;
}

function formatPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '-';
  return `${(v * 100).toFixed(digits)}%`;
}

function JBBreakdown({ detail }: { detail: JBFairPriceDetail }) {
  const keys = ['kb', 'molit', 'naver'] as const;
  const center3 = detail.forecast?.[3];
  return (
    <details className="jb-breakdown">
      <summary>JB 적정시세 · 예측 산출 근거 보기</summary>
      <div className="jb-breakdown-body">
        <section>
          <h4>JB 적정시세 — 수행달 가중치</h4>
          <p className="jb-formula">
            JB = KB×<b>{formatPct(detail.weights.kb, 0)}</b> + 실거래×
            <b>{formatPct(detail.weights.molit, 0)}</b> + 호가×
            <b>{formatPct(detail.weights.naver, 0)}</b> ={' '}
            <b>{formatEok(detail.fair_price)}</b>
          </p>
          <table className="jb-source-table">
            <thead>
              <tr>
                <th>소스</th>
                <th>그 달 대표값</th>
                <th>표본 사용</th>
                <th>가중치</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((k) => (
                <tr key={k}>
                  <td>{SOURCE_LABEL[k]}</td>
                  <td>{formatEok(detail.sources[k])}</td>
                  <td>{(detail.confidence[k] ?? 0) > 0 ? '✓' : '-'}</td>
                  <td>{formatPct(detail.weights[k], 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {detail.notes?.length > 0 && (
            <ul className="jb-notes">
              {detail.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
          <p className="jb-method-hint">
            ※ 산출식: JB = (그 달 KB 평균)·40% + (그 달 실거래 IQR-평균)·60% + (그 달 호가 IQR-평균)·0%.
            수행달에 실거래 표본이 없으면 KB 단독(100%) 폴백.
            호가는 단지별 수집이 안정화되면 활성 예정.
            <br />
            ※ 월 대표값 계산: KB 는 그 달 스냅샷의 산술평균, 실거래·호가는 그 달 표본에서 IQR(1.5×) 이상치 제거 후 평균.
            <br />
            ※ 위 표의 가중치는 항상 "수행달" 의 가용 데이터 기준으로 표기됩니다.
          </p>
        </section>

        {center3 && (
          <section>
            <h4>+3개월 예측 — 80% 신뢰구간</h4>
            <p className="jb-formula">
              중심값 <b>{formatEok(center3.predicted)}</b> · 하한{' '}
              <b>{formatEok(center3.lower)}</b> · 상한{' '}
              <b>{formatEok(center3.upper)}</b>
            </p>
            <p className="jb-method-hint">
              ※ 모델: log(JB<sub>t</sub>) = α + β·t 의 <b>지수가중 OLS</b> — 각 월 데이터에 weight w<sub>i</sub> = 0.85<sup>N−1−i</sup> (최근 월이 1, 1개월 전 0.85, 11개월 전 ≈ 0.17). 최근 정체·추세를 더 강하게 반영해 외삽이 덜 가팔라짐.
              <br />
              ※ 신뢰구간: 가중 잔차 σ<sub>resid,w</sub> × √(1 + 1/N + (t* − t̄<sub>w</sub>)²/Σw<sub>i</sub>(t<sub>i</sub> − t̄<sub>w</sub>)²) × Z<sub>80</sub>(=1.282). 외삽 거리(t* − t̄<sub>w</sub>)가 클수록 구간 폭 ↑.
              <br />
              ※ JB 월 시계열 6개 미만이거나 t 분산 0 이면 예측 생략.
            </p>
          </section>
        )}
      </div>
    </details>
  );
}

export default function AIMarketAnalysis({ analysis, jbDetail }: AIMarketAnalysisProps) {
  if (!analysis && !jbDetail) return null;

  return (
    <div className="ai-card">
      <h3>AI 시세 분석 결과</h3>
      <div className="ai-content">
        {analysis && <pre>{analysis}</pre>}
        {jbDetail && <JBBreakdown detail={jbDetail} />}
      </div>
    </div>
  );
}
