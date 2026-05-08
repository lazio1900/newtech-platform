// 담보 물건 기초 정보
export interface PropertyBasicData {
  complex_name?: string | null;
  address: string;
  units: number | null;
  corridor_type: string | null;
  age: number | null;
  area: number | null;
  exclusive_m2?: number | null;
  supply_m2?: number | null;
  location_score: number | null;
}

// 소유지분현황 (갑구)
export interface OwnershipEntry {
  name: string;
  reg_number: string;
  share: string;
  address: string;
  rank_number: number;
}

// 소유지분 제외 소유권 사항 (갑구)
export interface OwnershipOtherEntry {
  rank_number: number;
  purpose: string;
  receipt_info: string;
  details: string;
}

// (근)저당권 및 전세권 등 (을구)
export interface MortgageEntry {
  rank_number: string;
  purpose: string;
  receipt_info: string;
  main_details: string;
  target_owner: string;
}

// 담보 물건 권리 정보
export interface PropertyRightsData {
  ownership_entries: OwnershipEntry[];
  ownership_other_entries: OwnershipOtherEntry[];
  mortgage_entries: MortgageEntry[];
  max_bond_amount?: number;
  tenant_deposit?: number;
}

// 차주 재무 데이터 (연도별)
export interface FinancialYearData {
  year: number;
  assets: number;
  liabilities: number;
  equity: number;
  revenue: number;
  operating_profit: number;
  net_income: number;
}

// 차주 정보
export interface BorrowerData {
  company_name: string;
  business_number: string;
  financial_data: FinancialYearData[];
}

// 연대보증인 정보
export interface GuarantorData {
  name: string;
  credit_score_kcb: number;
  credit_score_nice: number;
  direct_debt: number;
  guarantee_debt: number;
}

// KB 시세
export interface KbPrice {
  estimated: number;
  low: number;
  high: number;
  trend: string;
}

// 국토교통부 실거래가
export interface MolitTransactions {
  recent_price: number;
  transaction_date: string;
  trend: string;
}

// 네이버페이 부동산 매매호가
export interface NaverListings {
  avg_asking: number;
  listing_count: number;
  trend: string;
}

// 크레딧 소스 데이터
export interface CreditSourcesData {
  kb_price: KbPrice;
  molit_transactions: MolitTransactions;
  naver_listings: NaverListings;
  jb_fair_price?: number | null;
}

// AI 권리 분석 - 항목별 요약
export interface RightsAnalysisDetail {
  gap_summary: string;
  eul_summary: string;
  seizure_summary: string;
  priority_summary: string;
}

// 사용자 정보
export interface User {
  user_id: string;
  company_name?: string;
  ceo_name?: string;
  business_number?: string;
  phone?: string;
  role?: string;
}

// 대출 신청
export interface LoanApplication {
  id: string;
  applicant_user_id?: number;
  auditor_user_id?: number | null;
  company_name: string;
  ceo_name: string;
  property_address: string;
  loan_amount: number;
  loan_duration: number;
  status: string;
  status_value?: string;
  // 단지/평형 매칭 (없으면 null)
  complex_id?: number | null;
  complex_name?: string | null;
  area_id?: number | null;
  exclusive_m2?: number | null;
  pyeong?: number | null;
  dong?: string | null;
  ho?: string | null;
  registry_ic_id?: number | null;
  memo?: string | null;
  created_at: string;
  decided_at?: string | null;
}

// KB 시세 이력 포인트
export interface PriceHistoryPoint {
  date: string;
  price: number;
}

// KB 시세 (이력 포함)
export interface KbPriceWithHistory extends KbPrice {
  history: PriceHistoryPoint[];
}

// 국토교통부 실거래가 (이력 포함)
export interface MolitTransactionsWithHistory extends MolitTransactions {
  history: PriceHistoryPoint[];
}

// 네이버 매매호가 (이력 포함)
export interface NaverListingsWithHistory extends NaverListings {
  history: PriceHistoryPoint[];
}

// JB 시세 미래 예측 (90% 신뢰구간)
export interface ForecastPoint {
  date: string;
  predicted: number;
  lower: number;
  upper: number;
}

// JB 적정시세 동적 가중치 산출 상세
export interface JBFairPriceDetail {
  fair_price: number;
  weights: Record<string, number>;
  sources: Record<string, number>;
  confidence: Record<string, number>;
  notes: string[];
  history: PriceHistoryPoint[];
  forecast: ForecastPoint[];
}

// 크레딧 소스 데이터 (차트용 이력 포함)
export interface CreditDataWithHistory {
  kb_price: KbPriceWithHistory;
  molit_transactions: MolitTransactionsWithHistory;
  naver_listings: NaverListingsWithHistory;
  jb_fair_price?: number | null;
  jb_detail?: JBFairPriceDetail | null;
}

// 입지 분석 점수
export interface LocationScores {
  station_walk: number;
  commute_time: number;
  units_score: number;
  school_walk: number;
  living_env: number;
  nature_env: number;
}

// AI 분석 결과
export interface AiAnalysis {
  property_analysis: string;
  rights_analysis: RightsAnalysisDetail;
  market_analysis: string;
  nearby_analysis?: string | null;
  comprehensive_opinion: string;
  auditor_recommendation?: string | null;
  location_scores?: LocationScores;
}

// 유사 물건
export interface SimilarProperty {
  name: string;
  sido: string;
  sigungu: string;
  address: string;
  units: number;
  age: number;
  area: number;
  exclusive_m2?: number | null;
  lat: number;
  lng: number;
  distance_m?: number | null;
  similarity?: number | null;
  recent_price: number;
  price_change_rate: number;
  price_diff_pct?: number | null;
}

// 인근 유사 물건 동향
export interface NearbyPropertyTrends {
  target_lat: number;
  target_lng: number;
  target_recent_price?: number | null;
  radius_m?: number | null;
  avg_change_rate?: number | null;
  similar_properties: SimilarProperty[];
}

// 평단가 추이 데이터 포인트
export interface PricePerPyeongPoint {
  date: string;
  complex: number;
  dong: number;
  sigungu: number;
}

// 평단가 추이
export interface PricePerPyeongTrend {
  complex_name: string;
  dong_name: string;
  sigungu_name: string;
  data: PricePerPyeongPoint[];
}

// 분석 응답 전체
export interface AnalysisResponse {
  property_basic_info: PropertyBasicData;
  property_rights_info: PropertyRightsData;
  borrower_info: BorrowerData;
  guarantor_info: GuarantorData;
  credit_data: CreditDataWithHistory;
  ai_analysis: AiAnalysis;
  nearby_property_trends?: NearbyPropertyTrends;
  price_per_pyeong_trend?: PricePerPyeongTrend;
}

// 모니터링 대출 항목
export interface MonitoringLoan {
  loan_id: string;
  auditor_name: string;
  company_name: string;
  ceo_name?: string;
  property_address: string;
  loan_amount: number;
  execution_date: string;
  execution_price: number;
  current_price: number;
  execution_ltv: number;
  current_ltv: number;
  ltv_change: number;
  signal: string;
  signal_label: string;
}

// 모니터링 요약
export interface MonitoringSummary {
  total_count: number;
  green_count: number;
  yellow_count: number;
  red_count: number;
  total_amount: number;
  avg_current_ltv: number;
}

// 모니터링 응답
export interface MonitoringResponse {
  loans: MonitoringLoan[];
  summary: MonitoringSummary;
}
