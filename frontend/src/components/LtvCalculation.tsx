import type { PropertyRightsData, CreditSourcesData } from '@/types/loan';

interface LtvCalculationProps {
  rightsData: PropertyRightsData;
  creditData: CreditSourcesData;
  loanAmount: number;
  interestRate?: number;
  loanDuration?: number;
}

export default function LtvCalculation({ rightsData, creditData, loanAmount, interestRate = 7.5, loanDuration = 12 }: LtvCalculationProps) {
  const maxBond = rightsData.max_bond_amount || 0;
  const tenantDeposit = rightsData.tenant_deposit || 0;
  const loan = loanAmount || 0;
  const total = maxBond + tenantDeposit + loan;

  const kbEstimated = creditData.kb_price.estimated;
  const jbFair = creditData.jb_fair_price ?? creditData.kb_price.low;

  const ltvJB = jbFair > 0 ? (total / jbFair) * 100 : 0;
  const ltvCurrent = kbEstimated > 0 ? (total / kbEstimated) * 100 : 0;

  const formatEok = (value: number): string => {
    if (!value) return '0원';
    const eok = value / 100000000;
    if (eok >= 1) {
      return eok % 1 === 0 ? `${eok.toFixed(0)}억원` : `${eok.toFixed(1)}억원`;
    }
    return `${(value / 10000).toLocaleString()}만원`;
  };

  const getLtvColor = (ltv: number): string => {
    if (ltv <= 70) return '#20c997';
    if (ltv <= 85) return '#FF8C00';
    return '#EF5350';
  };

  const getLtvLabel = (ltv: number): string => {
    if (ltv <= 70) return '안전';
    if (ltv <= 85) return '주의';
    return '위험';
  };

  return (
    <div className="info-card ltv-card">
      <h3>산출 LTV</h3>

      <table className="ltv-summary-table">
        <tbody>
          <tr>
            <td className="ltv-label">① 선순위 근저당권</td>
            <td className="ltv-amount">{formatEok(maxBond)}</td>
          </tr>
          <tr>
            <td className="ltv-label">② 선순위 임차인</td>
            <td className="ltv-amount">{formatEok(tenantDeposit)}</td>
          </tr>
          <tr>
            <td className="ltv-label">③ 대출신청금액</td>
            <td className="ltv-amount">{formatEok(loan)}</td>
          </tr>
          <tr>
            <td className="ltv-label">④ 적용금리</td>
            <td className="ltv-amount">{interestRate}%</td>
          </tr>
          <tr>
            <td className="ltv-label">⑤ 대출기간</td>
            <td className="ltv-amount">{loanDuration}개월</td>
          </tr>
          <tr className="ltv-total-row">
            <td className="ltv-label">합계 (①+②+③)</td>
            <td className="ltv-amount">{formatEok(total)}</td>
          </tr>
        </tbody>
      </table>

      <div className="ltv-result-grid">
        <div className="ltv-result-box">
          <div className="ltv-result-header">JB 적정시세 기준</div>
          <div className="ltv-result-sub">(KB×0.3 + 실거래×0.6 + 호가×0.1)</div>
          <div className="ltv-result-price">{formatEok(jbFair)}</div>
          <div
            className="ltv-value"
            style={{ color: getLtvColor(ltvJB) }}
          >
            {ltvJB.toFixed(1)}%
          </div>
          <span
            className="ltv-badge"
            style={{ backgroundColor: getLtvColor(ltvJB) }}
          >
            {getLtvLabel(ltvJB)}
          </span>
        </div>

        <div className="ltv-result-box">
          <div className="ltv-result-header">현재 시세 기준</div>
          <div className="ltv-result-sub">(KB 추정가)</div>
          <div className="ltv-result-price">{formatEok(kbEstimated)}</div>
          <div
            className="ltv-value"
            style={{ color: getLtvColor(ltvCurrent) }}
          >
            {ltvCurrent.toFixed(1)}%
          </div>
          <span
            className="ltv-badge"
            style={{ backgroundColor: getLtvColor(ltvCurrent) }}
          >
            {getLtvLabel(ltvCurrent)}
          </span>
        </div>
      </div>
    </div>
  );
}
