import apiClient from './client';

// 폐쇄망 등기부 DB(nice_rles_*) 보조 — 부동산고유번호 검색 + 결정적 요약 미리보기.
// REGISTRY_SOURCE=auto|db 에서만 동작(pdf 면 503).

export interface RegistryCandidate {
  rles_unq_no: string;
  road_address: string;
  jibun_address: string;
  unit: string;
  mortgage_count: number;
  seizure_count: number;
  inquiry_date: string;
}

export interface RegistryPreview {
  rles_unq_no: string;
  exists: boolean;
  property_address?: string;
  exclusive_m2?: number | null;
  inquiry_date?: string;
  mortgage_count?: number;
  seizure_count?: number;
  max_bond_amount?: number;
  owners?: string[];
}

export interface RegistrySearchParams {
  sido?: string;
  sigungu?: string;
  dong?: string;       // 읍면동명
  complex?: string;    // 단지명
  building?: string;   // 동
  unit?: string;       // 호
}

export const registryDbApi = {
  /** 주소(시도/시군구/읍면동/단지/동/호)로 적재된 등기부의 부동산고유번호 후보 검색. */
  search: async (params: RegistrySearchParams): Promise<RegistryCandidate[]> => {
    const { data } = await apiClient.get<{ candidates: RegistryCandidate[] }>(
      '/api/registry-db/search',
      { params },
    );
    return data.candidates;
  },

  /** 부동산고유번호의 등기부 결정적 요약(주소·근저당 합계·소유자·신선도). LLM 없음. */
  preview: async (unq: string): Promise<RegistryPreview> => {
    const { data } = await apiClient.get<RegistryPreview>(
      `/api/registry-db/${encodeURIComponent(unq)}`,
    );
    return data;
  },
};
