import type { BorrowerData, FinancialYearData } from '@/types/loan';

interface BorrowerInfoProps {
  data: BorrowerData | null | undefined;
}

const NONE = '정보 없음';

const cell = (v: number | null | undefined): string => {
  if (v == null) return '-';
  return `${(v / 100000000).toFixed(0)}억`;
};

export default function BorrowerInfo({ data }: BorrowerInfoProps) {
  if (!data) return null;

  const fin: FinancialYearData[] = data.financial_data ?? [];

  return (
    <div className="info-card">
      <h3>차주 정보 조회 영역</h3>
      <div className="info-content">
        <div className="info-row">
          <span className="label">대부업체 명칭:</span>
          <span className="value">{data.company_name || NONE}</span>
        </div>
        <div className="info-row">
          <span className="label">사업자번호:</span>
          <span className="value">{data.business_number || NONE}</span>
        </div>
        <div className="info-row">
          <span className="label">대표자명:</span>
          <span className="value">{data.ceo_name || NONE}</span>
        </div>

        <div className="financial-table-container">
          <h4>최근 3개년 재무 정보</h4>
          {fin.length === 0 ? (
            <div style={{ padding: 12, color: '#9CA3AF', fontSize: 13 }}>
              마스터에 등록된 재무 정보가 없습니다.
            </div>
          ) : (
            <table className="financial-table">
              <thead>
                <tr>
                  <th>연도</th>
                  <th>자산</th>
                  <th>부채</th>
                  <th>자본</th>
                  <th>매출</th>
                  <th>영업이익</th>
                  <th>당기순이익</th>
                </tr>
              </thead>
              <tbody>
                {fin.map((y) => (
                  <tr key={y.year}>
                    <td>{y.year}년</td>
                    <td>{cell(y.assets)}</td>
                    <td>{cell(y.liabilities)}</td>
                    <td>{cell(y.equity)}</td>
                    <td>{cell(y.revenue)}</td>
                    <td>{cell(y.operating_profit)}</td>
                    <td>{cell(y.net_income)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
