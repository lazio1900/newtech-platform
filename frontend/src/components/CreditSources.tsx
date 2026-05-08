import type { CreditSourcesData } from '@/types/loan';

interface CreditSourcesProps {
  data: CreditSourcesData | null | undefined;
}

export default function CreditSources({ data }: CreditSourcesProps) {
  if (!data) return null;

  const formatPrice = (price: number): string => {
    return `${(price / 100000000).toFixed(1)}억원`;
  };

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
            <span className="main-price">{formatPrice(data.molit_transactions.recent_price)}</span>
            <span className="date">{data.molit_transactions.transaction_date}</span>
          </div>
          <span className="trend">{data.molit_transactions.trend}</span>
        </div>
      </div>

      <div className="credit-box">
        <h4>최신 부동산 매매호가</h4>
        <div className="credit-content">
          <div className="price-info">
            <span className="main-price">{formatPrice(data.naver_listings.avg_asking)}</span>
            <span className="listing-count">매물 {data.naver_listings.listing_count}건</span>
          </div>
          <span className="trend">{data.naver_listings.trend}</span>
        </div>
      </div>
    </div>
  );
}
