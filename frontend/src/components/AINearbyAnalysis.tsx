import type { CSSProperties } from 'react';

interface AINearbyAnalysisProps {
  nearbyAnalysis: string | null | undefined;
  similarCount: number;
}

/**
 * 유사물건 종합 LLM 코멘트 카드. ai-card 클래스(하늘색).
 */
export default function AINearbyAnalysis({ nearbyAnalysis, similarCount }: AINearbyAnalysisProps) {
  const cardStyle: CSSProperties = {
    height: '100%',
    display: 'flex',
    flexDirection: 'column',
    boxSizing: 'border-box',
  };

  if (!nearbyAnalysis) {
    const emptyMessage = similarCount === 0
      ? '유사 단지 수집 데이터가 없어 AI 분석을 생성하지 못했습니다.'
      : `AI 분석 결과를 준비 중입니다. (인근 단지 ${similarCount}건)`;
    return (
      <div className="ai-card" style={cardStyle}>
        <h3>AI 유사물건 분석</h3>
        <div className="ai-content" style={{ padding: '20px 0', color: '#888', fontSize: 12, textAlign: 'center' }}>
          {emptyMessage}
        </div>
      </div>
    );
  }

  return (
    <div className="ai-card" style={cardStyle}>
      <h3>AI 유사물건 분석</h3>
      <div
        className="ai-content"
        style={{ fontSize: 13, lineHeight: 1.7, color: '#1A1A2E', flex: 1, overflow: 'auto' }}
      >
        <pre style={{
          whiteSpace: 'pre-wrap', wordWrap: 'break-word',
          fontFamily: 'inherit', fontSize: 13, lineHeight: 1.7, margin: 0,
        }}>{nearbyAnalysis}</pre>
      </div>
    </div>
  );
}
