import apiClient from './client';
import type { MonitoringLoan, MonitoringResponse } from '@/types/loan';

export const getMonitoringLoans = async (): Promise<MonitoringResponse> => {
  const { data } = await apiClient.get<MonitoringResponse>('/api/monitoring');
  return data;
};

export const getMonitoringLoanDetail = async (loanCode: string): Promise<MonitoringLoan> => {
  const { data } = await apiClient.get<MonitoringLoan>(`/api/monitoring/${loanCode}`);
  return data;
};

export const addMonitoringLoan = async (loanData: {
  company_name: string;
  ceo_name: string;
  property_address: string;
  loan_amount: number;
  execution_price: number;
}): Promise<{ status: string; loan?: MonitoringLoan }> => {
  // auditor_name은 백엔드가 토큰의 사용자로부터 도출
  const { data } = await apiClient.post('/api/monitoring', loanData);
  return data;
};
