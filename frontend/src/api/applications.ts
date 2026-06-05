import apiClient from './client';
import type { LoanApplication } from '@/types/loan';

// 한글 상태 라벨 → 백엔드 enum 매핑 (BE는 enum 값을 기대, FE는 historically 한글 사용)
const STATUS_KO_TO_EN: Record<string, string> = {
  '접수완료': 'received',
  '심사중': 'reviewing',
  '승인': 'approved',
  '반려': 'rejected',
  '보류': 'on_hold',
};

export interface SubmitApplicationPayload {
  company_name: string;
  ceo_name: string;
  business_number?: string | null;
  credit_score_nice?: number | null;
  credit_score_kcb?: number | null;
  property_address: string;
  loan_amount: number;
  loan_duration?: number;
  // 단지/평형 매칭 (선택)
  complex_id?: number | null;
  complex_name?: string | null;
  area_id?: number | null;
  exclusive_m2?: number | null;
  pyeong?: number | null;
  dong?: string | null;
  ho?: string | null;
  registry_ic_id?: number | null;
  rles_unq_no?: string | null;
}

export const updateApplication = async (
  appId: string,
  appData: SubmitApplicationPayload,
): Promise<{ status: string; application?: LoanApplication }> => {
  const { data } = await apiClient.put(`/api/applications/${appId}`, appData, { timeout: 60_000 });
  return data;
};

export const submitApplication = async (
  appData: SubmitApplicationPayload,
): Promise<{ status: string; application?: LoanApplication }> => {
  // 케이스 등록 후 backend 가 prefetch AI 분석을 BackgroundTask 로 띄우는데,
  // 그 시점에 일시 부하가 끼면 응답이 글로벌 30s 안에 못 와서 ECONNABORTED.
  // 케이스 등록은 일반적으로 빠르므로 안전치만 넓힌다.
  const { data } = await apiClient.post('/api/applications', appData, { timeout: 60_000 });
  return data;
};

export const getApplications = async (): Promise<LoanApplication[]> => {
  const { data } = await apiClient.get('/api/applications');
  return data;
};

export const updateApplicationStatus = async (
  appId: string,
  status: string,
  memo?: string,
): Promise<{ status: string; application?: LoanApplication }> => {
  const enumValue = STATUS_KO_TO_EN[status] ?? status;
  const { data } = await apiClient.put(`/api/applications/${appId}/status`, {
    status: enumValue,
    memo: memo ?? null,
  });
  return data;
};
