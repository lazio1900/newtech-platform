import { useState } from 'react';

interface AINearbyAnalysisProps {
  nearbyAnalysis: string | null | undefined;
  similarCount: number;
}

/**
 * 유사물건 종합 LLM 코멘트 카드. ai-card 클래스(하늘색).
 */
export default function AINearbyAnalysis({ nearbyAnalysis, similarCount }: AINearbyAnalysisProps) {
  const [showDetail, setShowDetail] = useState(false);

  if (!nearbyAnalysis) {
    return (
      <div className="ai-card">
        <h3>AI 유사물건 분석</h3>
        <div className="ai-content" style={{ padding: '20px 0', color: '#888', fontSize: 12, textAlign: 'center' }}>
          AI 분석 결과를 준비 중입니다. (인근 단지 {similarCount}건)
        </div>
      </div>
    );
  }

  // [종합 의견] 섹션 추출 — 미리보기로
  const overallMatch = nearbyAnalysis.match(/\[종합 의견\]\n([\s\S]*?)(?:\n\[|$)/);
  const overall = overallMatch ? overallMatch[1].trim() : '';

  return (
    <div className="ai-card">
      <h3>AI 유사물건 분석</h3>
      <div className="ai-content" style={{ fontSize: 13, lineHeight: 1.7, color: '#1A1A2E' }}>
        {!showDetail ? (
          <div style={{ whiteSpace: 'pre-wrap' }}>
            <strong style={{ color: '#FF8C00' }}>[종합 의견]</strong>
            <div style={{ marginTop: 6 }}>{overall || nearbyAnalysis.slice(0, 200) + '...'}</div>
          </div>
        ) : (
          <pre style={{
            whiteSpace: 'pre-wrap', wordWrap: 'break-word',
            fontFamily: 'inherit', fontSize: 13, lineHeight: 1.7, margin: 0,
          }}>{nearbyAnalysis}</pre>
        )}
      </div>
      <button
        onClick={() => setShowDetail(!showDetail)}
        style={{
          marginTop: 12, padding: '6px 14px', fontSize: 12, fontWeight: 600,
          color: '#fff', backgroundColor: showDetail ? '#051C48' : '#006FBD',
          border: 'none', borderRadius: 4, cursor: 'pointer',
        }}
      >
        {showDetail ? '간략히' : '상세 보기'}
      </button>
    </div>
  );
}
