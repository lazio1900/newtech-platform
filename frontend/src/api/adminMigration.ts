/**
 * 운영 전환 체크리스트 API 클라이언트.
 */
import apiClient from './client';

export interface ChecklistItem {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  link: string | null;
}

export interface ChecklistResponse {
  status: string;
  all_ok: boolean;
  items: ChecklistItem[];
}

export const adminMigrationApi = {
  checklist: async (): Promise<ChecklistResponse> => {
    const { data } = await apiClient.get<ChecklistResponse>(
      '/api/admin/migration/checklist',
      { timeout: 30_000 },
    );
    return data;
  },
};
