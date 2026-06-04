import type { GuarantorData } from '@/types/loan';

interface GuarantorInfoProps {
  data: GuarantorData | null | undefined;
}

const NONE = '정보 없음';

const formatAmount = (amount: number | null | undefined): string => {
  if (amount == null) return NONE;
  return `${(amount / 100000000).toFixed(1)}억원`;
};

export default function GuarantorInfo({ data }: GuarantorInfoProps) {
  if (!data) return null;

  return (
    <div className="info-card">
      <h3>연대보증인(대표자) 정보 조회 영역</h3>
      <div className="info-content">
        <div className="info-row">
          <span className="label">이름:</span>
          <span className="value">{data.name || NONE}</span>
        </div>
        <div className="info-row">
          <span className="label">신용점수 (KCB):</span>
          <span className="value">
            {data.credit_score_kcb != null ? `${data.credit_score_kcb}점` : NONE}
          </span>
        </div>
        <div className="info-row">
          <span className="label">신용점수 (NICE):</span>
          <span className="value">
            {data.credit_score_nice != null ? `${data.credit_score_nice}점` : NONE}
          </span>
        </div>
        <div className="info-row">
          <span className="label">직접채무:</span>
          <span className="value">{formatAmount(data.direct_debt)}</span>
        </div>
        <div className="info-row">
          <span className="label">보증채무:</span>
          <span className="value">{formatAmount(data.guarantee_debt)}</span>
        </div>
      </div>
    </div>
  );
}
