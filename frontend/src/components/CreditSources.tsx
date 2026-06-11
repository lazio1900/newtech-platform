import type { CreditSourcesData } from '@/types/loan';

interface CreditSourcesProps {
  data: CreditSourcesData | null | undefined;
}

export default function CreditSources({ data }: CreditSourcesProps) {
  if (!data) return null;

  const formatPrice = (price: number | null | undefined): string => {
    if (price == null) return '데이터 없음';
    return `${(price / 100000000).toFixed(2)}억원`;
  };

  const molit = data.molit_transactions;

  return (
    <div className="credit-sources">
      <div className="credit-box">
        <h4>최신 KB 시세</h4>
        <div className="credit-content">
          <div className="price-info">
            <span className="main-price">{formatPrice(data.kb_price.estimated)}</span>
            <span className="price-range">
              {formatPrice(data.kb_price.low)} ~ {formatPrice(data.kb_price.high)}
            </span>
          </div>
          <span className="trend">{data.kb_price.trend}</span>
        </div>
      </div>

      <div className="credit-box">
        <h4>최신 실거래가</h4>
        <div className="credit-content">
          <div className="price-info">
            <span className="main-price">{formatPrice(molit.recent_price)}</span>
            {molit.transaction_date && <span className="date">{molit.transaction_date}</span>}
          </div>
          <span className="trend">{molit.trend}</span>
        </div>
      </div>
    </div>
  );
}
