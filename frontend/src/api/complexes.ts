import apiClient from "./client"
import type { Area, Complex, ComplexCreate, ComplexLastRunMap, PaginatedComplexes, RegionCounts } from "@/types/complex"

export const complexesApi = {
  list: (params?: {
    skip?: number;
    limit?: number;
    is_active?: boolean;
    search?: string;
    region_code?: string;
    dong_code?: string;
  }) =>
    apiClient.get<PaginatedComplexes>("/api/complexes", { params }).then((r) => r.data),

  regionCounts: () =>
    apiClient.get<RegionCounts>("/api/complexes/region-counts").then((r) => r.data),

  get: (id: number) =>
    apiClient.get<Complex>(`/api/complexes/${id}`).then((r) => r.data),

  listAreas: (id: number) =>
    apiClient.get<Area[]>(`/api/complexes/${id}/areas`).then((r) => r.data),

  create: (data: ComplexCreate) =>
    apiClient.post<Complex>("/api/complexes", data).then((r) => r.data),

  update: (id: number, data: Partial<ComplexCreate>) =>
    apiClient.patch<Complex>(`/api/complexes/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    apiClient.delete(`/api/complexes/${id}`).then((r) => r.data),

  getSigunguList: (sidoCode: string) =>
    apiClient
      .get<{ code: string; name: string; lat: number | null; lng: number | null }[]>(
        "/api/complexes/regions/sigungu",
        { params: { sido_code: sidoCode } },
      )
      .then((r) => r.data),

  discoverRegion: (regionCode: string) =>
    apiClient
      .post<{
        region_code: string
        total_found: number
        new_registered: number
        already_exists: number
      }>("/api/complexes/discover-region", null, {
        params: { region_code: regionCode },
      })
      .then((r) => r.data),

  collect: (id: number) =>
    apiClient
      .post<{ message: string; run_id: number }>(
        `/api/complexes/${id}/collect`,
      )
      .then((r) => r.data),

  batchCollect: (complexIds: number[]) =>
    apiClient
      .post<{ message: string; run_id: number; count: number }>(
        "/api/complexes/batch-collect",
        { complex_ids: complexIds },
      )
      .then((r) => r.data),

  getRunStatus: (runId: number) =>
    apiClient
      .get<RunStatus>(`/api/complexes/runs/${runId}/status`)
      .then((r) => r.data),

  getLastRuns: () =>
    apiClient
      .get<ComplexLastRunMap>("/api/complexes/last-runs")
      .then((r) => r.data),
}

export interface RunStatusTask {
  task_key: string
  status: string
  items_collected: number
  items_saved: number
  error_message: string | null
  started_at: string | null
  finished_at: string | null
}

export interface RunStatus {
  run_id: number
  status: string
  started_at: string | null
  finished_at: string | null
  total_tasks: number
  success_count: number
  failed_count: number
  tasks: RunStatusTask[]
}
