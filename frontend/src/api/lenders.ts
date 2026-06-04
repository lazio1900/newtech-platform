import apiClient from './client';

export interface YearlyFinancial {
  year: number;
  assets?: number | null;
  liabilities?: number | null;
  equity?: number | null;
  revenue?: number | null;
  operating_profit?: number | null;
  net_income?: number | null;
}

export interface Lender {
  id: number;
  company_name: string;
  business_number: string | null;
  ceo_name: string | null;
  credit_score_nice: number | null;
  credit_score_kcb: number | null;
  direct_debt: number | null;
  guarantee_debt: number | null;
  financial_data: YearlyFinancial[] | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface LenderInput {
  company_name: string;
  business_number?: string | null;
  ceo_name?: string | null;
  credit_score_nice?: number | null;
  credit_score_kcb?: number | null;
  direct_debt?: number | null;
  guarantee_debt?: number | null;
  financial_data?: YearlyFinancial[] | null;
}

export const lendersApi = {
  async list(q?: string): Promise<Lender[]> {
    const { data } = await apiClient.get('/api/lenders', { params: q ? { q } : {} });
    return data;
  },
  async create(input: LenderInput): Promise<Lender> {
    const { data } = await apiClient.post('/api/lenders', input);
    return data;
  },
  async update(id: number, input: Partial<LenderInput>): Promise<Lender> {
    const { data } = await apiClient.put(`/api/lenders/${id}`, input);
    return data;
  },
  async remove(id: number): Promise<void> {
    await apiClient.delete(`/api/lenders/${id}`);
  },
};
