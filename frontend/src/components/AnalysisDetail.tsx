import BorrowerInfo from './BorrowerInfo';
import GuarantorInfo from './GuarantorInfo';
import PropertyBasicInfo from './PropertyBasicInfo';
import PropertyRightsInfo from './PropertyRightsInfo';
import CreditSources from './CreditSources';
import PriceCharts from './PriceCharts';
import AIPropertyAnalysis from './AIPropertyAnalysis';
import AIRightsAnalysis from './AIRightsAnalysis';
import AIMarketAnalysis from './AIMarketAnalysis';
import NearbyPropertyMap from './NearbyPropertyMap';
import NearbyPropertyList from './NearbyPropertyList';
import AINearbyAnalysis from './AINearbyAnalysis';
import PricePerPyeongChart from './PricePerPyeongChart';
import LtvCalculation from './LtvCalculation';
import AiComprehensiveOpinion from './AiComprehensiveOpinion';
import type { AnalysisResponse } from '@/types/loan';

interface AnalysisDetailProps {
  data: AnalysisResponse;
  loanAmount: number;
  interestRate?: number;
  loanDuration?: number;
}

// 신청목록>상세심사의 분석 섹션(담보/시세/유사물건/권리/차주/LTV/AI종합).
// 순수 표시용 — 승인/반려/심사의견서 등 액션은 호출부가 감싼다.
export default function AnalysisDetail({
  data,
  loanAmount,
  interestRate = 7.5,
  loanDuration = 12,
}: AnalysisDetailProps) {
  return (
    <>
      <h2 className="section-divider">담보 물건 분석</h2>
      <div className="layout-row">
        <PropertyBasicInfo data={data.property_basic_info} />
        <AIPropertyAnalysis
          analysis={data.ai_analysis.property_analysis}
          locationScores={data.ai_analysis.location_scores}
          complexScores={data.ai_analysis.complex_scores}
        />
      </div>

      <h2 className="section-divider">시세 분석</h2>
      {data.credit_data ? (
        <div className="layout-row-market">
          <div className="market-left">
            <CreditSources data={data.credit_data} />
            <PriceCharts data={data.credit_data} loanDuration={loanDuration} />
          </div>
          <div className="market-right">
            <AIMarketAnalysis
              analysis={data.ai_analysis.market_analysis}
              jbDetail={data.credit_data.jb_detail}
            />
          </div>
        </div>
      ) : (
        <div className="card daf-unavailable">시세 확인 불가 — 내부형식(CCTR_*)에 이 단지 시세 데이터가 없습니다.</div>
      )}

      <h2 className="section-divider">유사 물건 분석</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'stretch' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {data.nearby_property_trends?.target_lat != null && (
            <NearbyPropertyMap
              data={data.nearby_property_trends}
              targetAddress={data.property_basic_info.address}
            />
          )}
          <NearbyPropertyList
            data={data.nearby_property_trends}
          />
        </div>
        {/* 우측 셀은 absolute 로 띄워 높이를 좌측 카드에 맞추고, 길면 카드 내부에서 스크롤 */}
        <div style={{ position: 'relative', minHeight: 0 }}>
          <div style={{ position: 'absolute', inset: 0 }}>
            <AINearbyAnalysis
              nearbyAnalysis={data.ai_analysis.nearby_analysis}
              similarCount={data.nearby_property_trends?.similar_properties.length || 0}
            />
          </div>
        </div>
      </div>
      <div className="layout-row-full" style={{ marginTop: 16 }}>
        <PricePerPyeongChart
          data={data.price_per_pyeong_trend}
        />
      </div>

      <h2 className="section-divider">권리 분석</h2>
      <div className="layout-row">
        <PropertyRightsInfo
          data={data.property_rights_info}
        />
        <AIRightsAnalysis analysis={data.ai_analysis.rights_analysis} />
      </div>

      <h2 className="section-divider">차주 분석</h2>
      <div className="layout-row">
        <BorrowerInfo data={data.borrower_info} />
        <GuarantorInfo data={data.guarantor_info} />
      </div>

      <h2 className="section-divider">LTV 분석</h2>
      <div className="layout-row-full">
        {data.credit_data ? (
          <LtvCalculation
            rightsData={data.property_rights_info}
            creditData={data.credit_data}
            loanAmount={loanAmount}
            interestRate={interestRate}
            loanDuration={loanDuration}
          />
        ) : (
          <div className="card daf-unavailable">LTV 확인 불가 — 시세(분모) 데이터가 없습니다. 근저당 채권최고액 {data.property_rights_info.max_bond_amount.toLocaleString()}원만 확인됨.</div>
        )}
      </div>

      <h2 className="section-divider">AI 종합 의견</h2>
      <div className="layout-row-full">
        <AiComprehensiveOpinion opinion={data.ai_analysis.comprehensive_opinion} />
      </div>
    </>
  );
}
