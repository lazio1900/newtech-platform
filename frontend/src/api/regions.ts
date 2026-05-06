import apiClient from './client';

export interface RegionItem {
  code: string;
  name: string;
  count: number;
}

export interface DongItem {
  code: string;
  name: string;
}

export const regionsApi = {
  listSido: () =>
    apiClient.get<RegionItem[]>('/api/regions/sido').then((r) => r.data),

  listSigungu: (sidoCode: string) =>
    apiClient
      .get<RegionItem[]>('/api/regions/sigungu', { params: { sido: sidoCode } })
      .then((r) => r.data),

  listEupmyeondong: (sigunguCode: string) =>
    apiClient
      .get<DongItem[]>('/api/regions/eupmyeondong', { params: { sigungu: sigunguCode } })
      .then((r) => r.data),
};
