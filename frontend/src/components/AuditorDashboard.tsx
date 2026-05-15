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
import RegistryModal from './RegistryModal';
import MonitoringTab from './MonitoringTab';
import NearbyPropertyMap from './NearbyPropertyMap';
import NearbyPropertyList from './NearbyPropertyList';
import AINearbyAnalysis from './AINearbyAnalysis';
import PricePerPyeongChart from './PricePerPyeongChart';
import LtvCalculation from './LtvCalculation';
import AiComprehensiveOpinion from './AiComprehensiveOpinion';
import { analyzeProperty } from '@/api/analysis';
import { getApplications, updateApplicationStatus } from '@/api/applications';
import { addMonitoringLoan } from '@/api/monitoring';
import type { User, LoanApplication, AnalysisResponse } from '@/types/loan';
import AdminPanel from './AdminPanel';
import Settings from './Settings';
import UserProfileMenu from './UserProfileMenu';
import { getDefaultTab } from '@/lib/interfacePrefs';
import './AuditorDashboard.css';

type ActiveTab = 'dashboard' | 'direct' | 'applications' | 'monitoring' | 'my-account' | 'admin-users';

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

  // 직접조회 상태
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisData, setAnalysisData] = useState<AnalysisResponse | null>(null);
  const [showRegistryModal, setShowRegistryModal] = useState<boolean>(false);

  // 신청건 상태
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [selectedApp, setSelectedApp] = useState<LoanApplication | null>(null);
  const [appAnalysisData, setAppAnalysisData] = useState<AnalysisResponse | null>(null);
  const [appAnalysisError, setAppAnalysisError] = useState<string | null>(null);
  const [appLoading, setAppLoading] = useState<boolean>(false);
  const [showAppRegistryModal, setShowAppRegistryModal] = useState<boolean>(false);

  // 직접조회 대출금액, 금리, 대출기간
  const [directLoanAmount, setDirectLoanAmount] = useState<number>(0);
  const [directInterestRate, setDirectInterestRate] = useState<number>(7.5);
  const [directLoanDuration, setDirectLoanDuration] = useState<number>(12);
  const [directRegistryIcId, setDirectRegistryIcId] = useState<number | null>(null);

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
    setDirectLoanAmount(parseInt(String(payload.loanAmount)));
    setDirectInterestRate(payload.interestRate);
    setDirectLoanDuration(payload.duration);
    setDirectRegistryIcId(payload.options.registry_ic_id ?? null);
    setLoading(true);
    setError(null);
    try {
      const response = await analyzeProperty(
        payload.company,
        payload.address,
        payload.loanAmount,
        {
          complexId: payload.options.complex_id ?? null,
          areaId: payload.options.area_id ?? null,
          complexName: payload.options.complex_name ?? null,
          pyeong: payload.options.pyeong ?? null,
          registryIcId: payload.options.registry_ic_id ?? null,
          interestRate: payload.interestRate,
        },
      );
      setAnalysisData(response);
    } catch (err) {
      const e = err as { code?: string; message?: string; response?: { data?: { detail?: string } } };
      const isTimeout = e?.code === 'ECONNABORTED' || /timeout/i.test(e?.message || '');
      setError(
        isTimeout
          ? '분석에 시간이 오래 걸려 응답을 받지 못했습니다. 잠시 후 다시 시도해주세요.'
          : (e?.response?.data?.detail || e?.message || '분석 중 오류가 발생했습니다.'),
      );
    } finally {
      setLoading(false);
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
    return `${(value / 100000000).toFixed(1)}억원`;
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
    showModal: boolean,
    setShowModal: (v: boolean) => void,
    loanAmount: number,
    interestRate: number = 7.5,
    loanDuration: number = 12,
    registryIcId: number | null = null,
  ) => (
    <div className="content-layout">
      <h2 className="section-divider">담보 물건 분석</h2>
      <div className="layout-row">
        <PropertyBasicInfo data={data.property_basic_info} />
        <AIPropertyAnalysis
          analysis={data.ai_analysis.property_analysis}
          locationScores={data.ai_analysis.location_scores}
        />
      </div>

      <h2 className="section-divider">시세 분석</h2>
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

      <h2 className="section-divider">유사 물건 분석</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'stretch' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <NearbyPropertyMap
            data={data.nearby_property_trends}
            targetAddress={data.property_basic_info.address}
          />
          <NearbyPropertyList
            data={data.nearby_property_trends}
          />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <AINearbyAnalysis
            nearbyAnalysis={data.ai_analysis.nearby_analysis}
            similarCount={data.nearby_property_trends?.similar_properties.length || 0}
          />
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
          onViewPDF={() => setShowModal(true)}
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
        <LtvCalculation
          rightsData={data.property_rights_info}
          creditData={data.credit_data}
          loanAmount={loanAmount}
          interestRate={interestRate}
          loanDuration={loanDuration}
        />
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
          onClick={() => {
            if (selectedApp) handleStatusUpdate(selectedApp.id, '반려');
          }}
        >
          거절
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
                  execution_price: data.credit_data.kb_price.estimated
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

      {showModal && (
        <RegistryModal
          onClose={() => setShowModal(false)}
          icId={registryIcId}
        />
      )}

      {showReviewReport && (() => {
        const ri = data.property_rights_info;
        const kb = data.credit_data.kb_price;
        const molit = data.credit_data.molit_transactions;
        const naver = data.credit_data.naver_listings;
        const jbFair = data.credit_data.jb_fair_price ?? kb.low;
        const ls = data.ai_analysis.location_scores;
        const totalPrior = (ri.max_bond_amount || 0) + (ri.tenant_deposit || 0) + loanAmount;
        const ltvCurrent = kb.estimated > 0 ? (totalPrior / kb.estimated * 100).toFixed(1) : '-';
        const ltvJB = jbFair > 0 ? (totalPrior / jbFair * 100).toFixed(1) : '-';
        const nearbyProps = data.nearby_property_trends?.similar_properties || [];
        const pyeongData = data.price_per_pyeong_trend?.data || [];
        // 심사 상태: 신청건 분석이면 selectedApp.status, 직접분석이면 "검토 필요"
        const reviewStatus = selectedApp?.status || '검토 필요';

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
                  <h3>담보대출 심사의견서</h3>
                  <p className="report-date">작성일: {new Date().toLocaleDateString('ko-KR')}</p>
                </div>

                {/* 1. 기본 정보 */}
                <div className="report-section">
                  <h4>1. 기본 정보</h4>
                  <table className="report-table">
                    <tbody>
                      <tr>
                        <th>대부업체명</th>
                        <td>{data.borrower_info.company_name}</td>
                        <th>사업자등록번호</th>
                        <td>{data.borrower_info.business_number}</td>
                      </tr>
                      <tr>
                        <th>담보물건 주소</th>
                        <td colSpan={3}>{data.property_basic_info.address}</td>
                      </tr>
                      <tr>
                        <th>전용면적</th>
                        <td>{data.property_basic_info.area != null ? `${data.property_basic_info.area}평` : "N/A"}</td>
                        <th>세대수</th>
                        <td>{data.property_basic_info.units != null ? `${data.property_basic_info.units.toLocaleString()}세대` : "N/A"}</td>
                      </tr>
                      <tr>
                        <th>경과연수</th>
                        <td>{data.property_basic_info.age != null ? `${data.property_basic_info.age}년` : "N/A"}</td>
                        <th></th>
                        <td></td>
                      </tr>
                      <tr>
                        <th>입지점수</th>
                        <td>{data.property_basic_info.location_score != null ? `${data.property_basic_info.location_score}점` : "N/A"}</td>
                        <th>대출신청금액</th>
                        <td>{formatAmount(loanAmount)}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* 2. 차주(대부업체) 재무 정보 — 외부 신용평가 미연동, 더미 유지 */}
                <div className="report-section">
                  <h4>2. 차주 재무 정보 (최근 3개년)</h4>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>연도</th>
                        <th>총자산</th>
                        <th>총부채</th>
                        <th>자기자본</th>
                        <th>매출액</th>
                        <th>영업이익</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.borrower_info.financial_data.map((f) => (
                        <tr key={f.year}>
                          <td>{f.year}년</td>
                          <td>{formatAmount(f.assets)}</td>
                          <td>{formatAmount(f.liabilities)}</td>
                          <td>{formatAmount(f.equity)}</td>
                          <td>{formatAmount(f.revenue)}</td>
                          <td>{formatAmount(f.operating_profit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* 3. 연대보증인 — 등기부 소유자 정보 활용 */}
                <div className="report-section">
                  <h4>3. 연대보증인(담보제공자) 정보</h4>
                  <table className="report-table">
                    <tbody>
                      <tr>
                        <th>성명</th>
                        <td>{ri.ownership_entries?.[0]?.name || '-'}</td>
                        <th>최종지분</th>
                        <td>{ri.ownership_entries?.[0]?.share || '-'}</td>
                      </tr>
                      <tr>
                        <th>주소</th>
                        <td colSpan={3}>{ri.ownership_entries?.[0]?.address || '-'}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* 4. 등기 권리관계 */}
                <div className="report-section">
                  <h4>4. 등기 권리관계</h4>
                  <table className="report-table">
                    <tbody>
                      <tr>
                        <th>소유자</th>
                        <td colSpan={3}>{ri.ownership_entries?.[0]?.name ?? '-'} ({ri.ownership_entries?.[0]?.share ?? '-'})</td>
                      </tr>
                      <tr>
                        <th>을구 (근저당)</th>
                        <td colSpan={3}>
                          {ri.mortgage_entries?.map((m: { rank_number: string; purpose: string; main_details: string }, i: number) => (
                            <div key={i}>{m.rank_number}. {m.purpose} - {m.main_details.split('\n')[0]}</div>
                          ))}
                        </td>
                      </tr>
                      <tr>
                        <th>선순위 채권최고액</th>
                        <td>{formatAmount(ri.max_bond_amount)}</td>
                        <th>선순위 임차보증금</th>
                        <td>{formatAmount(ri.tenant_deposit)}</td>
                      </tr>
                      {ri.ownership_other_entries?.length > 0 && (
                        <tr className="warning-row">
                          <th>특이사항</th>
                          <td colSpan={3} className="warning">
                            {ri.ownership_other_entries.map((e: { purpose: string; details: string }, i: number) => (
                              <div key={i}>{e.purpose}: {e.details.split('\n')[0]}</div>
                            ))}
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                {/* 5. 시세 정보 */}
                <div className="report-section">
                  <h4>5. 시세 정보</h4>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>구분</th>
                        <th>시세</th>
                        <th>추세</th>
                        <th>비고</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>KB 추정가</td>
                        <td>{formatAmount(kb.estimated)}</td>
                        <td>{kb.trend}</td>
                        <td>하한 {formatAmount(kb.low)} ~ 상한 {formatAmount(kb.high)}</td>
                      </tr>
                      <tr>
                        <td>국토부 실거래가</td>
                        <td>{formatAmount(molit.recent_price)}</td>
                        <td>{molit.trend}</td>
                        <td>거래일 {molit.transaction_date}</td>
                      </tr>
                      <tr>
                        <td>네이버 매매호가</td>
                        <td>{formatAmount(naver.avg_asking)}</td>
                        <td>{naver.trend}</td>
                        <td>매물 {naver.listing_count}건</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* 6. 산출 LTV */}
                <div className="report-section">
                  <h4>6. 산출 LTV</h4>
                  <table className="report-table">
                    <tbody>
                      <tr>
                        <th>① 선순위 근저당권</th>
                        <td>{formatAmount(ri.max_bond_amount)}</td>
                        <th>② 선순위 임차인</th>
                        <td>{formatAmount(ri.tenant_deposit)}</td>
                      </tr>
                      <tr>
                        <th>③ 대출신청금액</th>
                        <td>{formatAmount(loanAmount)}</td>
                        <th>합계 (①+②+③)</th>
                        <td style={{fontWeight:700}}>{formatAmount(totalPrior)}</td>
                      </tr>
                      <tr>
                        <th>현재 시세 기준 LTV</th>
                        <td>{ltvCurrent}% (KB 추정가 {formatAmount(kb.estimated)})</td>
                        <th>JB 적정시세 기준 LTV</th>
                        <td>{ltvJB}% (JB 적정 {formatAmount(jbFair)})</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* 7. 입지 분석 점수 */}
                {ls && (
                <div className="report-section">
                  <h4>7. AI 입지 분석 점수</h4>
                  <table className="report-table score-table">
                    <thead>
                      <tr>
                        <th>역세권</th>
                        <th>노선 다양성</th>
                        <th>단지 규모</th>
                        <th>학군</th>
                        <th>생활환경</th>
                        <th>자연환경</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>{ls.station_walk}점</td>
                        <td>{ls.commute_time}점</td>
                        <td>{ls.units_score}점</td>
                        <td>{ls.school_walk}점</td>
                        <td>{ls.living_env}점</td>
                        <td>{ls.nature_env}점</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                )}

                {/* 8. 인근 유사물건 동향 */}
                {nearbyProps.length > 0 && (
                <div className="report-section">
                  <h4>8. 인근 유사물건 동향</h4>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>단지명</th>
                        <th>세대수</th>
                        <th>연식</th>
                        <th>면적</th>
                        <th>최근 거래가</th>
                        <th>3개월 변동률</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nearbyProps.map((p, i) => (
                        <tr key={i}>
                          <td>{p.name}</td>
                          <td>{p.units}세대</td>
                          <td>{p.age}년</td>
                          <td>{p.area}평</td>
                          <td>{formatAmount(p.recent_price)}</td>
                          <td style={{color: p.price_change_rate >= 0 ? '#20c997' : '#EF5350'}}>
                            {(p.price_change_rate * 100).toFixed(1)}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                )}

                {/* 9. 평단가 추이 */}
                {pyeongData.length > 0 && (
                <div className="report-section">
                  <h4>9. 단지/읍면동/시군구 평단가 추이</h4>
                  <table className="report-table">
                    <thead>
                      <tr>
                        <th>월</th>
                        <th>{data.price_per_pyeong_trend?.complex_name || '단지'} (만원/평)</th>
                        <th>{data.price_per_pyeong_trend?.dong_name || '읍면동'} (만원/평)</th>
                        <th>{data.price_per_pyeong_trend?.sigungu_name || '시군구'} (만원/평)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pyeongData.map((d, i) => (
                        <tr key={i}>
                          <td>{d.date}</td>
                          <td>{d.complex.toLocaleString()}</td>
                          <td>{d.dong.toLocaleString()}</td>
                          <td>{d.sigungu.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                )}

                {/* 10. AI 종합 의견 */}
                <div className="report-section">
                  <h4>10. AI 종합 의견</h4>
                  <div className="report-opinion-box">
                    {data.ai_analysis.comprehensive_opinion || '(AI 종합 의견 없음)'}
                  </div>
                </div>

                {/* 11. 심사역 종합 의견 */}
                <div className="report-section">
                  <h4>11. 심사역 종합 의견</h4>
                  <div className="report-opinion-box">
                    {auditorOpinion || '(의견 미입력)'}
                  </div>
                </div>

                {/* 12. 심사 결과 */}
                <div className="report-section">
                  <h4>12. 심사 결과</h4>
                  <div
                    className={`report-result ${reviewStatus === '승인' ? 'approved' : ''}`}
                    style={{
                      background:
                        reviewStatus === '승인' ? '#e6f9f0' :
                        reviewStatus === '반려' ? '#FEE2E2' :
                        reviewStatus === '심사중' ? '#FEF3C7' :
                        '#F1F5F9',
                      color:
                        reviewStatus === '승인' ? '#20c997' :
                        reviewStatus === '반려' ? '#991B1B' :
                        reviewStatus === '심사중' ? '#92400E' :
                        '#475569',
                    }}
                  >
                    {reviewStatus}
                  </div>
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
            className={`sidebar-btn ${activeTab === 'direct' ? 'active' : ''}`}
            onClick={() => setActiveTab('direct')}
          >
            직접조회하기
          </button>
          <button
            className={`sidebar-btn ${activeTab === 'applications' ? 'active' : ''}`}
            onClick={() => setActiveTab('applications')}
          >
            대부업체 신청건
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

        {/* 직접조회하기 탭 */}
        {activeTab === 'direct' && (
          <div className="direct-tab">
            <DirectAnalysisForm onAnalyze={handleAnalyze} loading={loading} />

            {(loading || analysisData || error) && (
              <div
                className="direct-result-modal-backdrop"
                onClick={() => {
                  if (loading) return;  // 분석 중엔 닫기 금지
                  setAnalysisData(null);
                  setError(null);
                }}
              >
                <div
                  className="direct-result-modal"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="direct-result-modal-header">
                    <h3>분석 결과</h3>
                    <button
                      className="direct-result-close"
                      disabled={loading}
                      onClick={() => { setAnalysisData(null); setError(null); }}
                      aria-label="닫기"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="direct-result-modal-body">
                    {loading && (
                      <div className="loading-message">
                        <div className="spinner"></div>
                        <p>분석 중입니다. 잠시만 기다려주세요...</p>
                      </div>
                    )}
                    {error && !loading && (
                      <div className="error-message">
                        <p>{error}</p>
                      </div>
                    )}
                    {analysisData && !loading && renderAnalysisResult(
                      analysisData, showRegistryModal, setShowRegistryModal,
                      directLoanAmount, directInterestRate, directLoanDuration,
                      directRegistryIcId,
                    )}
                  </div>
                </div>
              </div>
            )}
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
                      </tr>
                    </thead>
                    <tbody>
                      {applications.map((app) => (
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
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
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
                  appAnalysisData, showAppRegistryModal, setShowAppRegistryModal,
                  selectedApp.loan_amount, 7.5, selectedApp.loan_duration,
                  selectedApp.registry_ic_id ?? null,
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
