import { useState, useEffect } from 'react';
import DirectAnalysisForm, { type DirectAnalyzePayload } from './DirectAnalysisForm';
import BorrowerInfo from './BorrowerInfo';
import GuarantorInfo from './GuarantorInfo';
import PropertyBasicInfo from './PropertyBasicInfo';
import PropertyRightsInfo from './PropertyRightsInfo';
import CreditSources from './CreditSources';
import PriceCharts from './PriceCharts';
import AIPropertyAnalysis from './AIPropertyAnalysis';
import AIRightsAnalysis from './AIRightsAnalysis';
import AIMarketAnalysis from './AIMarketAnalysis';
import MonitoringTab from './MonitoringTab';
import NearbyPropertyMap from './NearbyPropertyMap';
import NearbyPropertyList from './NearbyPropertyList';
import AINearbyAnalysis from './AINearbyAnalysis';
import PricePerPyeongChart from './PricePerPyeongChart';
import LtvCalculation from './LtvCalculation';
import AiComprehensiveOpinion from './AiComprehensiveOpinion';
import { analyzeProperty } from '@/api/analysis';
import { getApplications, submitApplication, updateApplication, updateApplicationStatus } from '@/api/applications';
import { addMonitoringLoan } from '@/api/monitoring';
import type { User, LoanApplication, AnalysisResponse } from '@/types/loan';
import AdminPanel from './AdminPanel';
import LendersPanel from './LendersPanel';
import Settings from './Settings';
import UserProfileMenu from './UserProfileMenu';
import { getDefaultTab } from '@/lib/interfacePrefs';
import './AuditorDashboard.css';

type ActiveTab = 'dashboard' | 'direct' | 'lenders' | 'applications' | 'monitoring' | 'my-account' | 'admin-users';

interface AuditorDashboardProps {
  user: User;
  onLogout: () => void;
}

const STATUS_COLOR: Record<string, string> = {
  '접수완료': '#006FBD',
  '심사중': '#051C48',
  '승인': '#20c997',
  '반려': '#EF5350',
  '보류': '#9CA3AF',
};

export default function AuditorDashboard({ user, onLogout }: AuditorDashboardProps) {
  const [activeTab, setActiveTab] = useState<ActiveTab>(getDefaultTab());

  // 신청하기 폼 제출 상태
  const [submitting, setSubmitting] = useState<boolean>(false);
  // 신청건 수정 모달
  const [editingApp, setEditingApp] = useState<LoanApplication | null>(null);
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  // 신청 목록 필터
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterText, setFilterText] = useState<string>('');
  const [filterFromDate, setFilterFromDate] = useState<string>('');  // YYYY-MM-DD
  const [filterToDate, setFilterToDate] = useState<string>('');
  const [filterAmountMin, setFilterAmountMin] = useState<string>(''); // 억원 단위
  const [filterAmountMax, setFilterAmountMax] = useState<string>('');
  const [filterSort, setFilterSort] = useState<string>('created_desc');  // created_desc/created_asc/amount_desc/amount_asc

  // 신청건 상태
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [selectedApp, setSelectedApp] = useState<LoanApplication | null>(null);
  const [appAnalysisData, setAppAnalysisData] = useState<AnalysisResponse | null>(null);
  const [appAnalysisError, setAppAnalysisError] = useState<string | null>(null);
  const [appLoading, setAppLoading] = useState<boolean>(false);

  // 심사역 종합 의견
  const [auditorOpinion, setAuditorOpinion] = useState<string>('');
  const [opinionSaved, setOpinionSaved] = useState<boolean>(false);
  const [showReviewReport, setShowReviewReport] = useState<boolean>(false);
  const [showApproveConfirm, setShowApproveConfirm] = useState<boolean>(false);

  useEffect(() => {
    fetchApplications();
  }, []);

  useEffect(() => {
    if (activeTab === 'applications') {
      fetchApplications();
    }
  }, [activeTab]);

  const fetchApplications = async () => {
    try {
      const data = await getApplications();
      setApplications(data);
    } catch (err) {
      console.error('Failed to fetch applications:', err);
    }
  };

  const handleAnalyze = async (payload: DirectAnalyzePayload) => {
    if (!payload.ceoName.trim()) {
      alert("선택한 대부업체의 대표자명이 비어 있어 신청할 수 없습니다. '대부업체 등록' 탭에서 대표자명을 먼저 채워주세요.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await submitApplication({
        company_name: payload.company,
        ceo_name: payload.ceoName.trim(),
        business_number: payload.businessNumber.trim() || null,
        credit_score_nice: payload.creditScoreNice,
        credit_score_kcb: payload.creditScoreKcb,
        property_address: payload.address,
        loan_amount: payload.loanAmount,
        loan_duration: payload.duration,
        complex_id: payload.options.complex_id ?? null,
        complex_name: payload.options.complex_name ?? null,
        area_id: payload.options.area_id ?? null,
        pyeong: payload.options.pyeong ?? null,
        dong: payload.dong || null,
        ho: payload.ho || null,
        registry_ic_id: payload.options.registry_ic_id ?? null,
        rles_unq_no: payload.options.rles_unq_no ?? null,
      });
      alert(`신청건이 등록되었습니다 (ID: ${res.application?.id ?? '-'}). 대부업체 신청건 탭으로 이동합니다.`);
      await fetchApplications();
      setActiveTab('applications');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(`신청 실패: ${e?.response?.data?.detail || e?.message || '알 수 없는 오류'}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleEditApp = async (payload: DirectAnalyzePayload) => {
    if (!editingApp) return;
    if (!payload.ceoName.trim()) {
      alert("대표자명이 비어 있어 저장할 수 없습니다. '대부업체 등록' 탭에서 채워주세요.");
      return;
    }
    setEditSubmitting(true);
    try {
      await updateApplication(editingApp.id, {
        company_name: payload.company,
        ceo_name: payload.ceoName.trim(),
        business_number: payload.businessNumber.trim() || null,
        credit_score_nice: payload.creditScoreNice,
        credit_score_kcb: payload.creditScoreKcb,
        property_address: payload.address,
        loan_amount: payload.loanAmount,
        loan_duration: payload.duration,
        complex_id: payload.options.complex_id ?? null,
        complex_name: payload.options.complex_name ?? null,
        area_id: payload.options.area_id ?? null,
        pyeong: payload.options.pyeong ?? null,
        dong: payload.dong || null,
        ho: payload.ho || null,
        registry_ic_id: payload.options.registry_ic_id ?? null,
        rles_unq_no: payload.options.rles_unq_no ?? null,
      });
      setEditingApp(null);
      await fetchApplications();
      alert('신청건이 수정되었습니다.');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(`수정 실패: ${e?.response?.data?.detail || e?.message || '알 수 없는 오류'}`);
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleAppAnalyze = async (app: LoanApplication) => {
    setSelectedApp(app);
    setAppLoading(true);
    setAppAnalysisData(null);
    setAppAnalysisError(null);
    try {
      const response = await analyzeProperty(
        app.company_name,
        app.property_address,
        app.loan_amount,
        {
          complexId: app.complex_id ?? null,
          areaId: app.area_id ?? null,
          complexName: app.complex_name ?? null,
          pyeong: app.pyeong ?? null,
          applicationId: app.id,
        },
      );
      setAppAnalysisData(response);
    } catch (err) {
      console.error('Analysis error:', err);
      const e = err as { code?: string; message?: string; response?: { data?: { detail?: string } } };
      const isTimeout = e?.code === 'ECONNABORTED' || /timeout/i.test(e?.message || '');
      setAppAnalysisError(
        isTimeout
          ? '분석에 시간이 오래 걸려 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.'
          : (e?.response?.data?.detail || e?.message || '분석 요청에 실패했습니다.')
      );
    } finally {
      setAppLoading(false);
    }
  };

  const handleStatusUpdate = async (appId: string, status: string) => {
    try {
      await updateApplicationStatus(appId, status);
      fetchApplications();
      if (selectedApp && selectedApp.id === appId) {
        setSelectedApp(prev => prev ? { ...prev, status } : prev);
      }
    } catch (err) {
      console.error('Status update failed:', err);
    }
  };

  const formatAmount = (value: number | undefined | null): string => {
    if (!value) return '-';
    return `${(value / 100000000).toFixed(2)}억원`;
  };

  const getStatusBadge = (status: string): React.CSSProperties => {
    const colors: Record<string, string> = {
      '접수완료': '#006FBD',
      '심사중': '#051C48',
      '승인': '#20c997',
      '반려': '#EF5350'
    };
    return {
      backgroundColor: colors[status] || '#999',
      color: '#FFFFFF',
      padding: '4px 12px',
      borderRadius: '12px',
      fontSize: '12px',
      fontWeight: '600'
    };
  };

  const handleSaveOpinion = () => {
    setOpinionSaved(true);
    setTimeout(() => setOpinionSaved(false), 2000);
  };

  const renderAnalysisResult = (
    data: AnalysisResponse,
    loanAmount: number,
    interestRate: number = 7.5,
    loanDuration: number = 12,
  ) => (
    <div className="content-layout">
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

      <h2 className="section-divider">AI 종합 의견 및 심사역 의견</h2>
      <div className="layout-row-full">
        <AiComprehensiveOpinion opinion={data.ai_analysis.comprehensive_opinion} />
      </div>

      <div className="layout-row-full">
        <div className="opinion-card">
          <h3>심사역 종합 의견</h3>
          <textarea
            className="opinion-textarea"
            placeholder="심사 종합 의견을 입력하세요..."
            value={auditorOpinion}
            onChange={(e) => setAuditorOpinion(e.target.value)}
            rows={5}
          />
          <div className="opinion-footer">
            {opinionSaved && (
              <span className="opinion-saved-msg">저장되었습니다.</span>
            )}
            <button
              className="opinion-save-btn"
              onClick={handleSaveOpinion}
              disabled={!auditorOpinion.trim()}
            >
              저장
            </button>
          </div>
        </div>
      </div>

      <div className="final-actions">
        <button
          className="final-btn reject"
          onClick={async () => {
            if (!selectedApp) return;
            if (!window.confirm('반려하시겠습니까?')) return;
            await handleStatusUpdate(selectedApp.id, '반려');
            setSelectedApp(null);
            setAppAnalysisData(null);
            setAppAnalysisError(null);
          }}
        >
          반려
        </button>
        <button
          className="final-btn approve"
          onClick={async () => {
            if (selectedApp) {
              handleStatusUpdate(selectedApp.id, '승인');
              try {
                await addMonitoringLoan({
                  company_name: data.borrower_info.company_name,
                  ceo_name: selectedApp.ceo_name,
                  property_address: data.property_basic_info.address,
                  loan_amount: selectedApp.loan_amount,
                  execution_price: data.credit_data?.kb_price.estimated ?? 0
                });
              } catch (err) {
                console.error('Monitoring registration failed:', err);
              }
              setShowApproveConfirm(true);
            }
          }}
        >
          승인
        </button>
        <button
          className="final-btn report"
          onClick={() => setShowReviewReport(true)}
        >
          심사의견서 생성
        </button>
      </div>


      {showReviewReport && (() => {
        const ri = data.property_rights_info;
        // INTERNAL_ONLY: 시세 없으면 확인 불가 → 0/빈값으로 표시(보고서는 '-' 처리됨)
        const kb = data.credit_data?.kb_price ?? { estimated: 0, high: 0, low: 0, trend: '-', history: [] };
        const molit = data.credit_data?.molit_transactions ?? { recent_price: null, transaction_date: null, trend: '-', history: [] };
        const totalPrior = (ri.max_bond_amount || 0) + (ri.tenant_deposit || 0) + loanAmount;
        const ltvCurrent = kb.estimated > 0 ? (totalPrior / kb.estimated * 100).toFixed(1) : '-';
        // 실제 심사의견서(파란캐피탈 양식) — 담보/재무/채무 표는 백만원, 신청금액은 원.
        const fmtM = (won?: number | null) => (won ? Math.round(won / 1e6).toLocaleString() : '-');
        const b = data.borrower_info;
        const g = data.guarantor_info;
        const pbi = data.property_basic_info;
        const loanM = Math.round(loanAmount / 1e6);
        const fin2 = [...b.financial_data].sort((x, y) => y.year - x.year).slice(0, 2);
        const overallOpinion = auditorOpinion || data.ai_analysis.auditor_recommendation || '';
        const productName = '주택 근저당권부 질권대출';

        return (
        <div className="modal-overlay" onClick={() => setShowReviewReport(false)}>
          <div className="modal-content review-report-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>심사의견서</h2>
              <button className="modal-close-btn" onClick={() => setShowReviewReport(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="review-report-document">
                <div className="report-title">
                  <h3>㈜{b.company_name} {productName} {loanM.toLocaleString()}백만원 검토</h3>
                  <p className="report-date">작성일: {new Date().toLocaleDateString('ko-KR')}</p>
                  <table className="report-table" style={{ marginTop: 8 }}>
                    <tbody>
                      <tr><th>전결권자</th><td></td><th>검토자</th><td>{user.ceo_name || user.user_id}</td></tr>
                    </tbody>
                  </table>
                </div>

                {/* 1. 여신개요 */}
                <div className="report-section">
                  <h4>1. 여신개요</h4>
                  <div className="report-opinion-box">본 건은 ㈜{b.company_name}의 근저당권부 질권대출 신청건임.</div>
                </div>

                {/* 2. 신청현황 */}
                <div className="report-section">
                  <h4>2. 신청현황 <span style={{ fontWeight: 400, fontSize: 12, color: '#888' }}>[단위:원]</span></h4>
                  <table className="report-table">
                    <tbody>
                      <tr><th>대출상품</th><td>{productName}</td><th>차주명</th><td>㈜{b.company_name}</td></tr>
                      <tr><th>설정순위</th><td></td><th>상환방식</th><td></td></tr>
                      <tr><th>대출기간</th><td>{loanDuration}개월</td><th>대출금리</th><td>{interestRate != null ? `${interestRate}%` : ''}</td></tr>
                      <tr><th>대출금액</th><td>{loanAmount.toLocaleString()}</td><th>자금용도</th><td></td></tr>
                    </tbody>
                  </table>
                </div>

                {/* 3. 담보개요 */}
                <div className="report-section">
                  <h4>3. 담보개요 <span style={{ fontWeight: 400, fontSize: 12, color: '#888' }}>[단위:백만원]</span></h4>
                  <table className="report-table">
                    <thead>
                      <tr><th>NO</th><th>물건지 주소</th><th>면적(㎡)</th><th>KB시세</th><th>선순위 임차</th><th>선순위 근저당</th><th>대출금액</th><th>LTV</th></tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>1</td>
                        <td>{pbi.complex_name ? `${pbi.address} ${pbi.complex_name}` : pbi.address}</td>
                        <td>{pbi.exclusive_m2 ?? ''}</td>
                        <td>{fmtM(kb.estimated)}</td>
                        <td>{fmtM(ri.tenant_deposit)}</td>
                        <td>{fmtM(ri.max_bond_amount)}</td>
                        <td>{loanM.toLocaleString()}</td>
                        <td>{ltvCurrent}%</td>
                      </tr>
                      <tr><th colSpan={6} style={{ textAlign: 'right' }}>총 계</th><td>{loanM.toLocaleString()}</td><td></td></tr>
                    </tbody>
                  </table>
                </div>

                {/* 4. 채무관계인 채무자 현황 */}
                <div className="report-section">
                  <h4>4. 채무관계인 채무자 현황 <span style={{ fontWeight: 400, fontSize: 12, color: '#888' }}>[단위:백만원]</span></h4>
                  <table className="report-table">
                    <tbody>
                      <tr><th>사업자명</th><td>㈜{b.company_name}</td><th>사업자번호</th><td>{b.business_number || ''}</td></tr>
                      <tr><th>대표자명</th><td>{b.ceo_name || ''}</td><th>설립일자</th><td></td></tr>
                      <tr><th>주요주주현황</th><td></td><th>소재지</th><td></td></tr>
                    </tbody>
                  </table>
                  <table className="report-table" style={{ marginTop: 8 }}>
                    <thead>
                      <tr><th>재무상태</th><th>자산</th><th>부채</th><th>자본총계</th><th>자본금</th><th>매출액</th><th>영업이익</th><th>당기순이익</th></tr>
                    </thead>
                    <tbody>
                      {fin2.length > 0 ? fin2.map((f) => (
                        <tr key={f.year}>
                          <td>{String(f.year).slice(2)}.12.31</td>
                          <td>{fmtM(f.assets)}</td><td>{fmtM(f.liabilities)}</td><td>{fmtM(f.equity)}</td>
                          <td></td>
                          <td>{fmtM(f.revenue)}</td><td>{fmtM(f.operating_profit)}</td><td>{fmtM(f.net_income)}</td>
                        </tr>
                      )) : (<tr><td>-</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>)}
                    </tbody>
                  </table>
                  <table className="report-table" style={{ marginTop: 8 }}>
                    <thead><tr><th>보유채무</th><th>금융업권</th><th>잔액</th><th>비고</th></tr></thead>
                    <tbody>
                      <tr><th>직접채무</th><td>당 사</td><td>{fmtM(b.direct_debt)}</td><td>질권대출</td></tr>
                      <tr><th>보증채무</th><td>당 사</td><td>{fmtM(b.guarantee_debt)}</td><td></td></tr>
                    </tbody>
                  </table>
                </div>

                {/* 5. 채무관계인 연대보증인 현황 */}
                <div className="report-section">
                  <h4>5. 채무관계인 연대보증인 현황 <span style={{ fontWeight: 400, fontSize: 12, color: '#888' }}>[단위:백만원]</span></h4>
                  <table className="report-table">
                    <tbody>
                      <tr><th>성명</th><td>{g.name || ''}</td><th>생년월일</th><td></td></tr>
                      <tr><th>채무자관계</th><td>{g.name && g.name === b.ceo_name ? '대표' : ''}</td><th>NICE</th><td>{g.credit_score_nice ?? ''}</td></tr>
                    </tbody>
                  </table>
                  <table className="report-table" style={{ marginTop: 8 }}>
                    <thead><tr><th>보유채무</th><th>금융업권</th><th>잔액</th><th>비고</th></tr></thead>
                    <tbody>
                      <tr><th>직접채무</th><td></td><td>{fmtM(g.direct_debt)}</td><td></td></tr>
                      <tr><th>보증채무</th><td>당 사</td><td>{fmtM(g.guarantee_debt)}</td><td></td></tr>
                    </tbody>
                  </table>
                </div>

                {/* 6. 영업부서 의견 */}
                <div className="report-section">
                  <h4>6. 영업부서 의견</h4>
                  <table className="report-table">
                    <tbody>
                      <tr><th>담보</th><td>KB시세 {fmtM(kb.estimated)}백만원 / 최근실거래가 {fmtM(molit.recent_price)}백만원{molit.transaction_date ? ` (${molit.transaction_date})` : ''}</td></tr>
                    </tbody>
                  </table>
                  <div style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>검토의견</div>
                  <div className="report-opinion-box" style={{ minHeight: 48 }}></div>
                </div>

                {/* 7. 기업심사팀 의견 */}
                <div className="report-section">
                  <h4>7. 기업심사팀 의견</h4>
                  <div style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>긍정의견</div>
                  <div className="report-opinion-box" style={{ minHeight: 36 }}></div>
                  <div style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>부정의견</div>
                  <div className="report-opinion-box" style={{ minHeight: 36 }}></div>
                  <div style={{ fontWeight: 700, fontSize: 13, margin: '8px 0 4px' }}>종합의견</div>
                  <div className="report-opinion-box" style={{ minHeight: 48 }}>{overallOpinion}</div>
                </div>

                <div className="report-footer">
                  <p>심사자: {user.ceo_name || user.user_id}</p>
                  <p>작성일시: {new Date().toLocaleString('ko-KR')}</p>
                </div>
              </div>
            </div>
            <div className="modal-actions">
              <button className="btn-primary" onClick={() => {
                const reportEl = document.querySelector('.review-report-document');
                if (!reportEl) return;
                // Word 호환 HTML (.doc) — Word/한컴 등에서 그대로 열림.
                // 진짜 OOXML(.docx) 는 별도 라이브러리(docx) 필요.
                const html = `<!DOCTYPE html>
<html xmlns:o="urn:schemas-microsoft-com:office:office"
      xmlns:w="urn:schemas-microsoft-com:office:word"
      xmlns="http://www.w3.org/TR/REC-html40">
<head>
<meta charset="utf-8">
<title>심사의견서</title>
<!--[if gte mso 9]>
<xml>
  <w:WordDocument>
    <w:View>Print</w:View>
    <w:Zoom>100</w:Zoom>
    <w:DoNotOptimizeForBrowser/>
  </w:WordDocument>
</xml>
<![endif]-->
<style>
@page{size:A4;margin:2cm}
body{font-family:'Malgun Gothic','맑은 고딕',sans-serif;padding:0;color:#333}
h3{text-align:center;margin-bottom:4px}
.report-date{text-align:center;color:#666;font-size:13px;margin-bottom:24px}
table{width:100%;border-collapse:collapse;margin-bottom:16px}
th,td{border:1px solid #ccc;padding:8px 12px;font-size:13px;text-align:left}
th{background:#f5f5f5;font-weight:600}
h4{margin:20px 0 8px;font-size:14px;border-bottom:2px solid #051C48;padding-bottom:4px;color:#051C48}
.report-opinion-box{border:1px solid #ddd;padding:12px;min-height:60px;border-radius:4px;white-space:pre-wrap;font-size:13px;line-height:1.8}
.report-result{text-align:center;font-size:18px;font-weight:700;padding:12px;border-radius:8px}
.approved{background:#e6f9f0;color:#20c997}
.report-footer{margin-top:30px;text-align:right;font-size:12px;color:#666;border-top:1px solid #ccc;padding-top:12px}
.warning{color:#EF5350}
</style></head><body>${reportEl.innerHTML}</body></html>`;
                const blob = new Blob(['﻿', html], {
                  type: 'application/msword;charset=utf-8',
                });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `심사의견서_${data.borrower_info.company_name}_${new Date().toISOString().slice(0,10)}.doc`;
                a.click();
                URL.revokeObjectURL(url);
              }}>Word 다운로드</button>
              <button className="btn-primary" style={{ backgroundColor: '#666' }} onClick={() => setShowReviewReport(false)}>닫기</button>
            </div>
          </div>
        </div>
        );
      })()}

      {showApproveConfirm && (
        <div className="modal-overlay" onClick={() => setShowApproveConfirm(false)}>
          <div className="modal-content approve-confirm-modal" onClick={(e) => e.stopPropagation()}>
            <div className="approve-confirm-body">
              <div className="approve-confirm-icon">&#9989;</div>
              <p className="approve-confirm-msg">승인이 완료되었습니다.<br/>사후 모니터링 화면으로 넘어가시겠습니까?</p>
            </div>
            <div className="approve-confirm-actions">
              <button
                className="btn-primary"
                onClick={() => {
                  setShowApproveConfirm(false);
                  setActiveTab('monitoring');
                }}
              >
                이동
              </button>
              <button
                className="btn-primary"
                style={{ backgroundColor: '#666' }}
                onClick={() => setShowApproveConfirm(false)}
              >
                취소
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="auditor-dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <img
            src="/capital_CI.png"
            alt="JB우리캐피탈"
            className="header-logo clickable"
            onClick={() => setActiveTab('dashboard')}
          />
          <span className="header-divider">|</span>
          <h1>질권 담보 대출 업무 플랫폼</h1>
        </div>
        <div className="header-right">
          {/* 사용자 정보 / 로그아웃은 좌측 사이드바 하단 사용자 메뉴로 이동 */}
        </div>
      </header>

      <div className="dashboard-body">
        <nav className="sidebar">
          <button
            className={`sidebar-btn ${activeTab === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActiveTab('dashboard')}
          >
            대시보드
          </button>
          <button
            className={`sidebar-btn ${activeTab === 'lenders' ? 'active' : ''}`}
            onClick={() => setActiveTab('lenders')}
          >
            대부업체 등록
          </button>
          <button
            className={`sidebar-btn ${activeTab === 'direct' ? 'active' : ''}`}
            onClick={() => setActiveTab('direct')}
          >
            신청하기
          </button>
          <button
            className={`sidebar-btn ${activeTab === 'applications' ? 'active' : ''}`}
            onClick={() => {
              // 신청건 탭 클릭 시 항상 목록으로 — 선택된 건/분석 결과 초기화
              setSelectedApp(null);
              setAppAnalysisData(null);
              setAppAnalysisError(null);
              setActiveTab('applications');
            }}
          >
            신청 목록
            {applications.filter(a => a.status === '접수완료').length > 0 && (
              <span className="badge">
                {applications.filter(a => a.status === '접수완료').length}
              </span>
            )}
          </button>
          <button
            className={`sidebar-btn ${activeTab === 'monitoring' ? 'active' : ''}`}
            onClick={() => setActiveTab('monitoring')}
          >
            사후모니터링
          </button>

          {/* 하단 — 사용자 프로필 + 드롭다운 메뉴 (OpenWebUI 스타일) */}
          <div className="sidebar-bottom">
            <UserProfileMenu
              user={user}
              onOpenAccount={() => setActiveTab('my-account')}
              onOpenAdminPanel={() => setActiveTab('admin-users')}
              onLogout={onLogout}
            />
          </div>
        </nav>

        <div className="dashboard-content">
        {/* 대시보드 탭 */}
        {activeTab === 'dashboard' && (
          <div className="main-dashboard">
            <h2 className="main-dashboard-title">
              {user.ceo_name || user.user_id}님, 환영합니다.
            </h2>

            <div className="dashboard-cards">
              <div className="dash-card pending">
                <div className="dash-card-header">
                  <span className="dash-card-icon">&#128203;</span>
                  <span className="dash-card-label">신규 접수 신청건</span>
                </div>
                <div className="dash-card-body">
                  <span className="dash-card-count">
                    {applications.filter(a => a.status === '접수완료').length}
                  </span>
                  <span className="dash-card-unit">건</span>
                </div>
                <p className="dash-card-desc">승인/반려 처리가 되지 않은 신청건</p>
                <button
                  className="dash-card-link"
                  onClick={() => setActiveTab('applications')}
                >
                  바로가기 &rarr;
                </button>
              </div>

              <div className="dash-card reviewing">
                <div className="dash-card-header">
                  <span className="dash-card-icon">&#128269;</span>
                  <span className="dash-card-label">심사중</span>
                </div>
                <div className="dash-card-body">
                  <span className="dash-card-count">
                    {applications.filter(a => a.status === '심사중').length}
                  </span>
                  <span className="dash-card-unit">건</span>
                </div>
                <p className="dash-card-desc">현재 심사가 진행 중인 건</p>
                <button
                  className="dash-card-link"
                  onClick={() => setActiveTab('applications')}
                >
                  바로가기 &rarr;
                </button>
              </div>

              <div className="dash-card approved">
                <div className="dash-card-header">
                  <span className="dash-card-icon">&#9989;</span>
                  <span className="dash-card-label">승인 완료</span>
                </div>
                <div className="dash-card-body">
                  <span className="dash-card-count">
                    {applications.filter(a => a.status === '승인').length}
                  </span>
                  <span className="dash-card-unit">건</span>
                </div>
                <p className="dash-card-desc">승인 처리된 대출 신청건</p>
              </div>

              <div className="dash-card rejected">
                <div className="dash-card-header">
                  <span className="dash-card-icon">&#10060;</span>
                  <span className="dash-card-label">반려</span>
                </div>
                <div className="dash-card-body">
                  <span className="dash-card-count">
                    {applications.filter(a => a.status === '반려').length}
                  </span>
                  <span className="dash-card-unit">건</span>
                </div>
                <p className="dash-card-desc">반려 처리된 대출 신청건</p>
              </div>
            </div>
          </div>
        )}

        {/* 신청하기 탭 */}
        {activeTab === 'direct' && (
          <div className="direct-tab">
            <DirectAnalysisForm onAnalyze={handleAnalyze} loading={submitting} />
          </div>
        )}

        {/* 대부업체 등록 탭 */}
        {activeTab === 'lenders' && (
          <LendersPanel />
        )}

        {/* 신청건 수정 모달 — 신청 폼 그대로 prefill */}
        {editingApp && (
          <div
            style={{
              position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
              display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
              padding: 24, overflowY: 'auto',
            }}
            onClick={() => { if (!editSubmitting) setEditingApp(null); }}
          >
            <div
              style={{
                background: '#fff', borderRadius: 8, width: 960, maxWidth: '95vw',
                maxHeight: '95vh', overflowY: 'auto', padding: 24,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: '#051C48', fontWeight: 700 }}>
                  신청건 수정 — {editingApp.id}
                </h3>
                <button
                  type="button" disabled={editSubmitting}
                  onClick={() => setEditingApp(null)}
                  style={{
                    background: 'transparent', border: 'none', fontSize: 20,
                    cursor: editSubmitting ? 'wait' : 'pointer', color: '#9CA3AF',
                  }}
                  aria-label="닫기"
                >✕</button>
              </div>
              <DirectAnalysisForm
                onAnalyze={handleEditApp}
                loading={editSubmitting}
                submitLabel="저장"
                submitLabelBusy="저장 중..."
                initial={{
                  lenderBusinessNumber: editingApp.business_number ?? null,
                  lenderCompanyName: editingApp.company_name,
                  complexId: editingApp.complex_id ?? null,
                  areaId: editingApp.area_id ?? null,
                  dong: editingApp.dong ?? null,
                  ho: editingApp.ho ?? null,
                  registryIcId: editingApp.registry_ic_id ?? null,
                  rlesUnqNo: editingApp.rles_unq_no ?? null,
                  loanAmount: editingApp.loan_amount,
                  loanDuration: editingApp.loan_duration,
                }}
              />
            </div>
          </div>
        )}

        {/* 대부업체 신청건 탭 */}
        {activeTab === 'applications' && (
          <div className="applications-tab">
            {!selectedApp ? (
              <div className="app-list-card">
                <h2>대부업체 신청 목록</h2>
                {applications.length === 0 ? (
                  <p className="empty-text">접수된 신청건이 없습니다.</p>
                ) : (() => {
                  const q = filterText.trim().toLowerCase();
                  // 금액은 억원 단위 입력 → 원 단위로 변환해 비교
                  const minWon = filterAmountMin.trim() ? Number(filterAmountMin) * 100000000 : null;
                  const maxWon = filterAmountMax.trim() ? Number(filterAmountMax) * 100000000 : null;
                  // 날짜는 YYYY-MM-DD 형식. created_at "YYYY-MM-DD HH:MM" 앞 10자 비교
                  const filtered = applications.filter((a) => {
                    if (filterStatus !== 'all' && a.status !== filterStatus) return false;
                    if (q) {
                      const hay = [a.id, a.company_name, a.ceo_name, a.complex_name || '', a.property_address || '']
                        .join(' ').toLowerCase();
                      if (!hay.includes(q)) return false;
                    }
                    if (minWon != null && (a.loan_amount ?? 0) < minWon) return false;
                    if (maxWon != null && (a.loan_amount ?? 0) > maxWon) return false;
                    if (filterFromDate) {
                      const d = (a.created_at || '').slice(0, 10);
                      if (d < filterFromDate) return false;
                    }
                    if (filterToDate) {
                      const d = (a.created_at || '').slice(0, 10);
                      if (d > filterToDate) return false;
                    }
                    return true;
                  });
                  // 정렬
                  filtered.sort((x, y) => {
                    if (filterSort === 'amount_desc') return (y.loan_amount ?? 0) - (x.loan_amount ?? 0);
                    if (filterSort === 'amount_asc') return (x.loan_amount ?? 0) - (y.loan_amount ?? 0);
                    if (filterSort === 'created_asc') return (x.created_at || '').localeCompare(y.created_at || '');
                    return (y.created_at || '').localeCompare(x.created_at || '');  // created_desc default
                  });
                  const counts = applications.reduce<Record<string, number>>((m, a) => {
                    m[a.status] = (m[a.status] || 0) + 1;
                    return m;
                  }, {});
                  const todayStr = new Date().toISOString().slice(0, 10);
                  const daysAgoStr = (n: number) => {
                    const d = new Date(); d.setDate(d.getDate() - n);
                    return d.toISOString().slice(0, 10);
                  };
                  const resetAll = () => {
                    setFilterStatus('all'); setFilterText('');
                    setFilterFromDate(''); setFilterToDate('');
                    setFilterAmountMin(''); setFilterAmountMax('');
                  };
                  const isFiltered = filterStatus !== 'all' || filterText || filterFromDate
                    || filterToDate || filterAmountMin || filterAmountMax;
                  const inp = (extra?: React.CSSProperties): React.CSSProperties => ({
                    padding: '6px 10px', border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 13, ...extra,
                  });
                  const chip = (active: boolean): React.CSSProperties => ({
                    padding: '4px 12px', borderRadius: 999, fontSize: 12, fontWeight: 600,
                    cursor: 'pointer', border: '1px solid', userSelect: 'none',
                    background: active ? '#006FBD' : '#fff',
                    color: active ? '#fff' : '#374151',
                    borderColor: active ? '#006FBD' : '#D1D5DB',
                  });
                  return (
                  <>
                  {/* 빠른 프리셋 */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, color: '#6B7280', marginRight: 4 }}>빠른 필터:</span>
                    <span style={chip(!isFiltered)} onClick={resetAll}>전체</span>
                    <span
                      style={chip(filterStatus === '접수완료' && !filterAmountMin && !filterAmountMax && !filterFromDate)}
                      onClick={() => { resetAll(); setFilterStatus('접수완료'); }}
                    >미결 ({counts['접수완료'] || 0})</span>
                    <span
                      style={chip(filterFromDate === todayStr && filterToDate === todayStr)}
                      onClick={() => { setFilterFromDate(todayStr); setFilterToDate(todayStr); }}
                    >오늘 접수</span>
                    <span
                      style={chip(filterFromDate === daysAgoStr(7) && !filterToDate)}
                      onClick={() => { setFilterFromDate(daysAgoStr(7)); setFilterToDate(''); }}
                    >최근 7일</span>
                    <span
                      style={chip(filterAmountMin === '5' && !filterAmountMax)}
                      onClick={() => { setFilterAmountMin('5'); setFilterAmountMax(''); }}
                    >고액 (5억+)</span>
                  </div>
                  {/* 상세 필터 */}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8, flexWrap: 'wrap' }}>
                    <input
                      type="text"
                      value={filterText}
                      onChange={(e) => setFilterText(e.target.value)}
                      placeholder="신청번호/업체/대표/단지/주소"
                      style={inp({ flex: 1, minWidth: 220 })}
                    />
                    <select
                      value={filterStatus}
                      onChange={(e) => setFilterStatus(e.target.value)}
                      style={inp()}
                    >
                      <option value="all">전체 상태</option>
                      <option value="접수완료">접수완료 ({counts['접수완료'] || 0})</option>
                      <option value="심사중">심사중 ({counts['심사중'] || 0})</option>
                      <option value="승인">승인 ({counts['승인'] || 0})</option>
                      <option value="반려">반려 ({counts['반려'] || 0})</option>
                      <option value="보류">보류 ({counts['보류'] || 0})</option>
                    </select>
                    <select
                      value={filterSort}
                      onChange={(e) => setFilterSort(e.target.value)}
                      style={inp()}
                    >
                      <option value="created_desc">최신순</option>
                      <option value="created_asc">오래된순</option>
                      <option value="amount_desc">금액 ↓</option>
                      <option value="amount_asc">금액 ↑</option>
                    </select>
                    {isFiltered && (
                      <button
                        type="button"
                        onClick={resetAll}
                        style={{ ...inp(), background: '#fff', color: '#374151', cursor: 'pointer' }}
                      >초기화</button>
                    )}
                    <span style={{ fontSize: 12, color: '#6B7280', marginLeft: 'auto' }}>
                      {filtered.length} / {applications.length} 건
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, color: '#6B7280' }}>신청일:</span>
                    <input
                      type="date" value={filterFromDate}
                      onChange={(e) => setFilterFromDate(e.target.value)}
                      style={inp()}
                    />
                    <span style={{ color: '#9CA3AF' }}>~</span>
                    <input
                      type="date" value={filterToDate}
                      onChange={(e) => setFilterToDate(e.target.value)}
                      style={inp()}
                    />
                    <span style={{ fontSize: 12, color: '#6B7280', marginLeft: 12 }}>금액(억):</span>
                    <input
                      type="number" min={0} step={0.1}
                      value={filterAmountMin}
                      onChange={(e) => setFilterAmountMin(e.target.value)}
                      placeholder="최소"
                      style={inp({ width: 100 })}
                    />
                    <span style={{ color: '#9CA3AF' }}>~</span>
                    <input
                      type="number" min={0} step={0.1}
                      value={filterAmountMax}
                      onChange={(e) => setFilterAmountMax(e.target.value)}
                      placeholder="최대"
                      style={inp({ width: 100 })}
                    />
                  </div>
                  {filtered.length === 0 ? (
                    <p className="empty-text">필터 조건에 해당하는 신청건이 없습니다.</p>
                  ) : (
                  <table className="app-table">
                    <thead>
                      <tr>
                        <th>신청번호</th>
                        <th>대부업체명</th>
                        <th>대표이사</th>
                        <th>단지명</th>
                        <th>담보물건 주소</th>
                        <th>신청금액</th>
                        <th>금리</th>
                        <th>대출기간</th>
                        <th>신청일시</th>
                        <th>상태</th>
                        <th>심사</th>
                        <th>수정</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((app) => (
                        <tr key={app.id}>
                          <td>{app.id}</td>
                          <td>{app.company_name}</td>
                          <td>{app.ceo_name}</td>
                          <td>{app.complex_name || '-'}</td>
                          <td className="address-cell">{app.property_address}</td>
                          <td>{formatAmount(app.loan_amount)}</td>
                          <td>7.5%</td>
                          <td>{app.loan_duration}개월</td>
                          <td>{app.created_at}</td>
                          <td>
                            <span style={getStatusBadge(app.status)}>
                              {app.status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="review-btn"
                              onClick={() => handleAppAnalyze(app)}
                            >
                              상세심사
                            </button>
                          </td>
                          <td>
                            <button
                              type="button"
                              onClick={() => setEditingApp(app)}
                              style={{
                                padding: '6px 12px', background: '#fff', color: '#006FBD',
                                border: '1px solid #006FBD', borderRadius: 6,
                                fontSize: 13, fontWeight: 600, cursor: 'pointer',
                              }}
                            >
                              수정
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  )}
                  </>
                  );
                })()}
              </div>
            ) : (
              <div className="app-detail">
                <div className="app-detail-header">
                  <div className="app-detail-topbar">
                    <button
                      className="back-to-list-btn"
                      onClick={() => { setSelectedApp(null); setAppAnalysisData(null); }}
                    >
                      ← 목록
                    </button>
                    <span className="app-detail-id">신청번호 <strong>{selectedApp.id}</strong></span>
                    <span className="app-detail-status status-badge"
                          style={{ backgroundColor: STATUS_COLOR[selectedApp.status] || '#999' }}>
                      {selectedApp.status}
                    </span>
                  </div>

                  <div className="app-detail-property">
                    <div className="property-primary">
                      {selectedApp.complex_name && (
                        <span className="property-complex">{selectedApp.complex_name}</span>
                      )}
                      {selectedApp.exclusive_m2 != null && (
                        <span className="property-meta">
                          {selectedApp.exclusive_m2.toFixed(2)}㎡
                          {selectedApp.pyeong ? ` (${selectedApp.pyeong}평)` : ''}
                        </span>
                      )}
                    </div>
                    <div className="property-address">{selectedApp.property_address}</div>
                  </div>

                  <div className="app-detail-loan">
                    <div className="loan-info-cell">
                      <span className="loan-info-label">신청업체</span>
                      <span className="loan-info-value">
                        {selectedApp.company_name}
                        <span className="loan-info-sub"> · {selectedApp.ceo_name}</span>
                      </span>
                    </div>
                    <div className="loan-info-cell">
                      <span className="loan-info-label">신청금액</span>
                      <span className="loan-info-value strong">{formatAmount(selectedApp.loan_amount)}</span>
                    </div>
                    <div className="loan-info-cell">
                      <span className="loan-info-label">적용금리</span>
                      <span className="loan-info-value">7.5%</span>
                    </div>
                    <div className="loan-info-cell">
                      <span className="loan-info-label">대출기간</span>
                      <span className="loan-info-value">{selectedApp.loan_duration}개월</span>
                    </div>
                    <div className="loan-info-cell">
                      <span className="loan-info-label">신청일시</span>
                      <span className="loan-info-value">{selectedApp.created_at}</span>
                    </div>
                  </div>
                </div>

                {appLoading && (
                  <div className="loading-message">
                    <div className="spinner"></div>
                    <p>신청건 분석 중입니다...</p>
                  </div>
                )}

                {appAnalysisData && !appLoading && renderAnalysisResult(
                  appAnalysisData,
                  selectedApp.loan_amount, 7.5, selectedApp.loan_duration,
                )}

                {!appLoading && !appAnalysisData && appAnalysisError && (
                  <div style={{
                    padding: 24, margin: '16px 0',
                    background: '#FEE2E2', borderRadius: 8,
                    color: '#991B1B', fontSize: 14, lineHeight: 1.6,
                  }}>
                    <strong style={{ display: 'block', marginBottom: 6 }}>분석 실패</strong>
                    {appAnalysisError}
                    <button
                      type="button"
                      onClick={() => handleAppAnalyze(selectedApp)}
                      style={{
                        marginTop: 12, padding: '6px 14px', fontSize: 13, fontWeight: 600,
                        color: '#fff', background: '#991B1B', border: 'none',
                        borderRadius: 4, cursor: 'pointer',
                      }}
                    >
                      다시 시도
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* 사후모니터링 탭 */}
        {activeTab === 'monitoring' && (
          <MonitoringTab />
        )}

        {/* 설정 탭 (계정 정보 + 화면 인터페이스 서브탭) */}
        {activeTab === 'my-account' && (
          <Settings user={user} />
        )}

        {/* 관리자 패널 — admin 전용. 내부 서브탭(사용자 / LLM 연결) */}
        {activeTab === 'admin-users' && user.role === 'admin' && (
          <AdminPanel />
        )}
        </div>
      </div>
    </div>
  );
}
