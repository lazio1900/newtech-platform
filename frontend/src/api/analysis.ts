import apiClient from './client';
import type { AnalysisResponse } from '@/types/loan';

interface AnalyzeOptions {
  complexId?: number | null;
  areaId?: number | null;
  complexName?: string | null;
  pyeong?: number | null;
}

export const analyzeProperty = async (
  companyName: string,
  address: string,
  loanAmount: number,
  options: AnalyzeOptions = {},
): Promise<AnalysisResponse> => {
  const { data } = await apiClient.post('/api/analyze', {
    company_name: companyName,
    property_address: address,
    loan_amount: loanAmount,
    complex_id: options.complexId ?? null,
    area_id: options.areaId ?? null,
    complex_name: options.complexName ?? null,
    pyeong: options.pyeong ?? null,
  });
  return data.data;
};

export const getSuggestions = async (field: string, query: string): Promise<string[]> => {
  const { data } = await apiClient.get('/api/suggestions', { params: { field, query } });
  return data;
};
