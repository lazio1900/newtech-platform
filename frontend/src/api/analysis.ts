import apiClient from './client';
import type { AnalysisResponse } from '@/types/loan';

interface AnalyzeOptions {
  complexId?: number | null;
  areaId?: number | null;
  complexName?: string | null;
  pyeong?: number | null;
  applicationId?: string | null;
  registryIcId?: number | null;
  interestRate?: number | null;
  ceoName?: string | null;
  businessNumber?: string | null;
  creditScoreNice?: number | null;
  creditScoreKcb?: number | null;
}

export const analyzeProperty = async (
  companyName: string,
  address: string,
  loanAmount: number,
  options: AnalyzeOptions = {},
): Promise<AnalysisResponse> => {
  // 콜드 캐시 시 LLM 5개 + MinerU 초기화로 30s 넘을 수 있음. nginx proxy_read_timeout(120s) 범위 내.
  const { data } = await apiClient.post('/api/analyze', {
    company_name: companyName,
    property_address: address,
    loan_amount: loanAmount,
    complex_id: options.complexId ?? null,
    area_id: options.areaId ?? null,
    complex_name: options.complexName ?? null,
    pyeong: options.pyeong ?? null,
    application_id: options.applicationId ?? null,
    registry_ic_id: options.registryIcId ?? null,
    interest_rate: options.interestRate ?? null,
    ceo_name: options.ceoName ?? null,
    business_number: options.businessNumber ?? null,
    credit_score_nice: options.creditScoreNice ?? null,
    credit_score_kcb: options.creditScoreKcb ?? null,
  }, { timeout: 180_000 });
  return data.data;
};

export const getSuggestions = async (field: string, query: string): Promise<string[]> => {
  const { data } = await apiClient.get('/api/suggestions', { params: { field, query } });
  return data;
};
