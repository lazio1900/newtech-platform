import apiClient from './client';

export interface RegistryRequestIn {
  address: string;
  dong?: string | null;
  ho?: string | null;
  type?: string;        // 등기부등본 타입 (예: 토지/건물/집합)
  complex_id?: number | null;  // backend 가 지번/도로명 후보 chain 구성용
  force_refresh?: boolean;
}

export interface RegistryRequestOut {
  id: number;
  ic_id: number | null;
  status: string;       // pending/issuing/completed/failed
  pdf_url: string | null;
  cost: number;
  cached: boolean;
  error_message: string | null;
  // 4단계 chain 중 실제로 매칭에 성공한 후보 — 잘못된 등기부 가져왔을 때 확인용
  matched_address?: string | null;
  matched_dong?: string | null;
  matched_ho?: string | null;
}

export interface RegistryAreaSuggestion {
  exclusive_m2: number | null;          // 등기부 표제부에서 추출한 전용면적
  suggested_area_id: number | null;     // 가장 가까운 KB area
  areas: Array<{ id: number; exclusive_m2: number; pyeong: number | null }>;
}

/**
 * 등기부등본 발급 요청.
 * newtech-platform backend 가 등기부등본api 로 X-Internal-Token 과 함께 forward.
 */
export const registryApi = {
  request: async (payload: RegistryRequestIn): Promise<RegistryRequestOut> => {
    // backend 가 최대 4단계 chain (지번/도로명 × 단지명 유무) 으로 IROS 매칭 시도.
    // 각 단계가 30s+ 걸릴 수 있어 합계는 그 이상. nginx proxy_read_timeout 도 동일하게 ↑.
    const { data } = await apiClient.post<RegistryRequestOut>(
      '/api/registry/request',
      payload,
      { timeout: 240_000 },
    );
    return data;
  },

  /** PDF 직접 업로드 — IROS 검색 실패/우회 케이스. 음수 ic_id 로 발급분과 구분. */
  upload: async (params: {
    file: File;
    address: string;
    dong?: string | null;
    ho?: string | null;
    type?: string;
  }): Promise<RegistryRequestOut> => {
    const form = new FormData();
    form.append('file', params.file);
    form.append('address', params.address);
    if (params.dong) form.append('dong', params.dong);
    if (params.ho) form.append('ho', params.ho);
    form.append('type', params.type || '집합건물');
    const { data } = await apiClient.post<RegistryRequestOut>(
      '/api/registry/upload',
      form,
      {
        timeout: 60_000,
        // FormData 인데 글로벌 default(application/json) 가 잡히면 boundary 없이 가서 422.
        // 명시적으로 multipart 로 두면 axios 가 boundary 를 채워 넣는다.
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    );
    return data;
  },

  /** 발급 상태 조회 (폴링용) */
  get: async (icId: number): Promise<RegistryRequestOut> => {
    const { data } = await apiClient.get<RegistryRequestOut>(`/api/registry/${icId}`);
    return data;
  },

  /** 등기부 표제부 → 전용면적 + 추천 area_id (수정용 후보 목록 포함) */
  getAreaSuggestion: async (
    icId: number,
    complexId: number,
  ): Promise<RegistryAreaSuggestion> => {
    const { data } = await apiClient.get<RegistryAreaSuggestion>(
      `/api/registry/${icId}/area`,
      { params: { complex_id: complexId } },
    );
    return data;
  },

  /** PDF 다운로드 URL — backend proxy 경로 (auth 헤더 필요해서 직접 a href X) */
  pdfUrl: (icId: number): string => `/api/registry/${icId}/pdf`,

  /** PDF 를 blob 으로 받아 새 탭/다운로드 처리 (Authorization 헤더 자동 첨부). */
  openPdf: async (icId: number): Promise<void> => {
    const res = await apiClient.get(`/api/registry/${icId}/pdf`, {
      responseType: 'blob',
    });
    const blob = new Blob([res.data], { type: 'application/pdf' });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, '_blank');
    if (!win) {
      // 팝업 차단 시 다운로드로 fallback
      const a = document.createElement('a');
      a.href = url;
      a.download = `registry_${icId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  },
};
