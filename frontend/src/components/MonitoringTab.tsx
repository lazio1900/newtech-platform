import { useState, useEffect, useMemo } from 'react';
import { analyzeProperty } from '@/api/analysis';
import { getMonitoringLoans, reevaluateAllMonitoring } from '@/api/monitoring';
import AnalysisDetail from './AnalysisDetail';
import type { MonitoringLoan, MonitoringSummary, AnalysisResponse } from '@/types/loan';
import './MonitoringTab.css';

export default function MonitoringTab() {
  const [loans, setLoans] = useState<MonitoringLoan[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [reevaluating, setReevaluating] = useState<boolean>(false);
  const [selectedLoan, setSelectedLoan] = useState<MonitoringLoan | null>(null);
  const [showDetailModal, setShowDetailModal] = useState<boolean>(false);
  const [detailData, setDetailData] = useState<AnalysisResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState<boolean>(false);

  // 정렬
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  // 필터
  const [filterAuditor, setFilterAuditor] = useState<string>('');
  const [filterCompany, setFilterCompany] = useState<string>('');
  const [filterSignal, setFilterSignal] = useState<string>('');

  useEffect(() => {
    void initLoad();
  }, []);

  // 진입 시 최신 시세로 재평가 후 표시 (현재 LTV/신호등이 실시간 반영되도록)
  const initLoad = async () => {
    setLoading(true);
    try {
      const data = await reevaluateAllMonitoring();
      setLoans(data.loans);
    } catch (err) {
      console.error('재평가 실패, 일반 조회로 대체:', err);
      try {
        const d = await getMonitoringLoans();
        setLoans(d.loans);
      } catch (e) {
        console.error('Failed to fetch monitoring data:', e);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleReevaluate = async () => {
    setReevaluating(true);
    try {
      const data = await reevaluateAllMonitoring();
      setLoans(data.loans);
    } catch (err) {
      console.error('재평가 실패:', err);
    } finally {
      setReevaluating(false);
    }
  };

  const lastEvaluated = useMemo(() => {
    const stamps = loans.map(l => l.last_evaluated_at).filter(Boolean) as string[];
    return stamps.length ? stamps.sort().slice(-1)[0] : null;
  }, [loans]);

  // 필터 옵션 추출
  const auditorOptions = useMemo(() =>
    [...new Set(loans.map(l => l.auditor_name))].sort(),
    [loans]
  );
  const companyOptions = useMemo(() =>
    [...new Set(loans.map(l => l.company_name))].sort(),
    [loans]
  );

  // 필터만 적용 (요약 카드 재계산 입력 — 정렬과 무관)
  const filteredLoans = useMemo(() => {
    let result = loans;
    if (filterAuditor) result = result.filter(l => l.auditor_name === filterAuditor);
    if (filterCompany) result = result.filter(l => l.company_name === filterCompany);
    if (filterSignal) result = result.filter(l => l.signal === filterSignal);
    return result;
  }, [loans, filterAuditor, filterCompany, filterSignal]);

  // 상단 요약 — 필터 적용된 행 기준으로 재계산
  const summary: MonitoringSummary = useMemo(() => {
    const rows = filteredLoans;
    const total = rows.length;
    const avg = total
      ? Math.round((rows.reduce((s, r) => s + r.current_ltv, 0) / total) * 10) / 10
      : 0;
    return {
      total_count: total,
      green_count: rows.filter(r => r.signal === 'green').length,
      yellow_count: rows.filter(r => r.signal === 'yellow').length,
      red_count: rows.filter(r => r.signal === 'red').length,
      total_amount: rows.reduce((s, r) => s + r.loan_amount, 0),
      avg_current_ltv: avg,
    };
  }, [filteredLoans]);

  // 정렬 핸들러
  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const getSortIndicator = (key: string) => {
    if (sortKey !== key) return <span className="sort-icon inactive">↕</span>;
    return <span className="sort-icon active">{sortDir === 'asc' ? '▲' : '▼'}</span>;
  };

  // 정렬 적용
  const processedLoans = useMemo(() => {
    const result = [...filteredLoans];
    if (sortKey) {
      result.sort((a, b) => {
        let aVal = (a as unknown as Record<string, unknown>)[sortKey];
        let bVal = (b as unknown as Record<string, unknown>)[sortKey];
        if (typeof aVal === 'string' && typeof bVal === 'string') {
          aVal = aVal.toLowerCase();
          bVal = bVal.toLowerCase();
        }
        if ((aVal as number | string) < (bVal as number | string)) return sortDir === 'asc' ? -1 : 1;
        if ((aVal as number | string) > (bVal as number | string)) return sortDir === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return result;
  }, [filteredLoans, sortKey, sortDir]);

  const hasActiveFilters = filterAuditor || filterCompany || filterSignal;

  const clearFilters = () => {
    setFilterAuditor('');
    setFilterCompany('');
    setFilterSignal('');
  };

  const handleLoanClick = async (loan: MonitoringLoan) => {
    setSelectedLoan(loan);
    setShowDetailModal(true);
    setDetailLoading(true);
    setDetailData(null);

    try {
      // application_id 가 있으면 백엔드가 당시 심사 박제(스냅샷)를 그대로 반환
      const response = await analyzeProperty(
        loan.company_name,
        loan.property_address,
        loan.loan_amount,
        {
          applicationId: loan.application_id ?? undefined,
          complexId: loan.complex_id ?? null,
          areaId: loan.area_id ?? null,
        }
      );
      setDetailData(response);
    } catch (err) {
      console.error('Analysis error:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeModal = () => {
    setShowDetailModal(false);
    setSelectedLoan(null);
    setDetailData(null);
  };

  const formatAmount = (value: number | undefined | null): string => {
    if (!value) return '-';
    return `${(value / 100000000).toFixed(2)}억원`;
  };

  const getSignalStyle = (signal: string): React.CSSProperties => {
    const colors: Record<string, { bg: string; color: string; border: string }> = {
      green: { bg: '#E8F5E9', color: '#2E7D32', border: '#4CAF50' },
      yellow: { bg: '#FFF8E1', color: '#F57F17', border: '#FFC107' },
      red: { bg: '#FFEBEE', color: '#C62828', border: '#EF5350' }
    };
    const c = colors[signal] || colors.green;
    return {
      backgroundColor: c.bg,
      color: c.color,
      border: `2px solid ${c.border}`,
      padding: '4px 12px',
      borderRadius: '16px',
      fontSize: '12px',
      fontWeight: '700',
      display: 'inline-flex',
      alignItems: 'center',
      gap: '4px'
    };
  };

  const getSignalDot = (signal: string) => {
    const colors: Record<string, string> = { green: '#4CAF50', yellow: '#FFC107', red: '#EF5350' };
    return (
      <span style={{
        width: 10, height: 10, borderRadius: '50%',
        backgroundColor: colors[signal] || '#999',
        display: 'inline-block'
      }} />
    );
  };

  const getLtvChangeDisplay = (change: number): string => {
    if (change > 0) return `+${change}%p`;
    return `${change}%p`;
  };

  return (
    <div className="monitoring-tab">
      {/* 요약 카드 — 필터 반영 */}
      <div className="monitoring-summary">
        <div className="summary-card total">
          <span className="summary-label">총 관리 건수</span>
          <span className="summary-value">{summary.total_count}건</span>
        </div>
        <div className="summary-card green">
          <span className="summary-label">안전</span>
          <span className="summary-value">{summary.green_count}건</span>
        </div>
        <div className="summary-card yellow">
          <span className="summary-label">주의</span>
          <span className="summary-value">{summary.yellow_count}건</span>
        </div>
        <div className="summary-card red">
          <span className="summary-label">위험</span>
          <span className="summary-value">{summary.red_count}건</span>
        </div>
        <div className="summary-card amount">
          <span className="summary-label">총 대출 잔액</span>
          <span className="summary-value">{formatAmount(summary.total_amount)}</span>
        </div>
        <div className="summary-card ltv">
          <span className="summary-label">평균 현재 LTV</span>
          <span className="summary-value">{summary.avg_current_ltv}%</span>
        </div>
      </div>

      {/* 대출 목록 테이블 */}
      <div className="monitoring-table-card">
        <div className="monitoring-table-header">
          <h2>취급 대출 사후모니터링</h2>
          <div className="monitoring-header-right">
            {lastEvaluated && (
              <span className="monitoring-last-eval">최근 재평가 {lastEvaluated}</span>
            )}
            <button className="reevaluate-btn" onClick={handleReevaluate} disabled={reevaluating || loading}>
              {reevaluating ? '재평가 중…' : '시세 재평가'}
            </button>
            <span className="monitoring-count">
              {hasActiveFilters
                ? `${processedLoans.length} / ${loans.length}건`
                : `${loans.length}건`
              }
            </span>
          </div>
        </div>

        {/* 필터 바 */}
        <div className="monitoring-filters">
          <div className="filter-group">
            <label>담당자</label>
            <select value={filterAuditor} onChange={(e) => setFilterAuditor(e.target.value)}>
              <option value="">전체</option>
              {auditorOptions.map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label>대부업체</label>
            <select value={filterCompany} onChange={(e) => setFilterCompany(e.target.value)}>
              <option value="">전체</option>
              {companyOptions.map(name => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="filter-group">
            <label>상태</label>
            <select value={filterSignal} onChange={(e) => setFilterSignal(e.target.value)}>
              <option value="">전체</option>
              <option value="green">안전</option>
              <option value="yellow">주의</option>
              <option value="red">위험</option>
            </select>
          </div>
          {hasActiveFilters && (
            <button className="filter-clear-btn" onClick={clearFilters}>
              필터 초기화
            </button>
          )}
        </div>

        <table className="monitoring-table">
          <thead>
            <tr>
              <th className="sortable-th" onClick={() => handleSort('loan_id')}>
                대출번호 {getSortIndicator('loan_id')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('auditor_name')}>
                담당자 {getSortIndicator('auditor_name')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('company_name')}>
                신청 대부업체 {getSortIndicator('company_name')}
              </th>
              <th>담보물건 주소</th>
              <th className="sortable-th" onClick={() => handleSort('loan_amount')}>
                대출금액 {getSortIndicator('loan_amount')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('execution_date')}>
                실행일자 {getSortIndicator('execution_date')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('execution_ltv')}>
                실행일 LTV {getSortIndicator('execution_ltv')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('current_ltv')}>
                현재 LTV {getSortIndicator('current_ltv')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('ltv_change')}>
                LTV 변동 {getSortIndicator('ltv_change')}
              </th>
              <th className="sortable-th" onClick={() => handleSort('signal')}>
                상태 {getSortIndicator('signal')}
              </th>
            </tr>
          </thead>
          <tbody>
            {processedLoans.length === 0 ? (
              <tr>
                <td colSpan={10} className="empty-table-text">
                  {loading ? '불러오는 중입니다…' : hasActiveFilters ? '필터 조건에 해당하는 데이터가 없습니다.' : '데이터가 없습니다.'}
                </td>
              </tr>
            ) : (
              processedLoans.map((loan) => (
                <tr key={loan.loan_id}>
                  <td className="loan-id-cell">
                    <button className="loan-id-link" onClick={() => handleLoanClick(loan)}>
                      {loan.loan_id}
                    </button>
                    {loan.reevaluable === false && <span className="loan-unlinked" title="원신청건 미연동 — 시세 재평가 불가">미연동</span>}
                  </td>
                  <td>{loan.auditor_name}</td>
                  <td>{loan.company_name}</td>
                  <td className="address-cell">{loan.property_address}</td>
                  <td>{formatAmount(loan.loan_amount)}</td>
                  <td>{loan.execution_date}</td>
                  <td>{loan.execution_ltv}%</td>
                  <td className={`ltv-cell ${loan.signal}`}>{loan.current_ltv}%</td>
                  <td className={`ltv-change ${loan.ltv_change > 0 ? 'up' : loan.ltv_change < 0 ? 'down' : ''}`}>
                    {getLtvChangeDisplay(loan.ltv_change)}
                  </td>
                  <td>
                    <span style={getSignalStyle(loan.signal)}>
                      {getSignalDot(loan.signal)}
                      {loan.signal_label}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 상세심사 팝업 — 신청목록>상세심사와 동일 분석 화면 */}
      {showDetailModal && selectedLoan && (
        <div className="monitoring-modal-overlay" onClick={closeModal}>
          <div className="monitoring-modal" onClick={(e) => e.stopPropagation()}>
            <div className="monitoring-modal-header">
              <div>
                <h2>대출 상세 - {selectedLoan.loan_id}</h2>
                <p className="modal-subtitle">
                  {selectedLoan.company_name} | {selectedLoan.property_address}
                </p>
              </div>
              <button className="modal-close-btn" onClick={closeModal}>&times;</button>
            </div>

            <div className="monitoring-loan-summary">
              <div className="loan-summary-item">
                <span className="ls-label">담당자</span>
                <span className="ls-value">{selectedLoan.auditor_name}</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">실행일</span>
                <span className="ls-value">{selectedLoan.execution_date}</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">대출금액</span>
                <span className="ls-value">{formatAmount(selectedLoan.loan_amount)}</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">실행일 시세</span>
                <span className="ls-value">{formatAmount(selectedLoan.execution_price)}</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">현재 시세</span>
                <span className="ls-value">{formatAmount(selectedLoan.current_price)}</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">실행일 LTV</span>
                <span className="ls-value">{selectedLoan.execution_ltv}%</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">현재 LTV</span>
                <span className={`ls-value ${selectedLoan.signal}`}>{selectedLoan.current_ltv}%</span>
              </div>
              <div className="loan-summary-item">
                <span className="ls-label">상태</span>
                <span style={getSignalStyle(selectedLoan.signal)}>
                  {getSignalDot(selectedLoan.signal)}
                  {selectedLoan.signal_label}
                </span>
              </div>
            </div>

            <div className="monitoring-modal-body">
              {detailLoading && (
                <div className="loading-message">
                  <div className="spinner"></div>
                  <p>당시 심사 결과를 불러오는 중입니다...</p>
                </div>
              )}

              {detailData && !detailLoading && (
                <div className="content-layout">
                  <AnalysisDetail data={detailData} loanAmount={selectedLoan.loan_amount} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
