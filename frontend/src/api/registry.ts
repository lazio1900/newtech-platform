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

  /** 발급 상태 조회 (폴링용) */
  get: async (icId: number): Promise<RegistryRequestOut> => {
    const { data } = await apiClient.get<RegistryRequestOut>(`/api/registry/${icId}`);
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
