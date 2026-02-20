import { useState, useCallback, useRef } from "react"
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query"
import { complexesApi } from "@/api/complexes"
import type { ComplexCreate } from "@/types/complex"

export function useComplexes(params?: {
  is_active?: boolean
  skip?: number
  limit?: number
  search?: string
  region_code?: string
}) {
  return useQuery({
    queryKey: ["complexes", params],
    queryFn: () => complexesApi.list(params),
    placeholderData: keepPreviousData,
  })
}

export function useRegionCounts() {
  return useQuery({
    queryKey: ["complexes", "regionCounts"],
    queryFn: () => complexesApi.regionCounts(),
  })
}

export function useComplex(id: number) {
  return useQuery({
    queryKey: ["complexes", id],
    queryFn: () => complexesApi.get(id),
    enabled: id > 0,
  })
}

export function useCreateComplex() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ComplexCreate) => complexesApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["complexes"] }),
  })
}

export function useUpdateComplex() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ComplexCreate> }) =>
      complexesApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["complexes"] }),
  })
}

export function useDeleteComplex() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => complexesApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["complexes"] }),
  })
}

export function useSigunguList(sidoCode: string) {
  return useQuery({
    queryKey: ["sigungu", sidoCode],
    queryFn: () => complexesApi.getSigunguList(sidoCode),
    enabled: !!sidoCode,
  })
}

export function useDiscoverRegion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (regionCode: string) => complexesApi.discoverRegion(regionCode),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["complexes"] })
    },
  })
}

export function useCollectComplex() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => complexesApi.collect(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] })
      qc.invalidateQueries({ queryKey: ["complexLastRuns"] })
    },
  })
}

export function useBatchCollectComplexes() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (complexIds: number[]) => complexesApi.batchCollect(complexIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs"] })
      qc.invalidateQueries({ queryKey: ["complexLastRuns"] })
    },
  })
}

export function useRunStatus(runId: number | null) {
  return useQuery({
    queryKey: ["runStatus", runId],
    queryFn: () => complexesApi.getRunStatus(runId!),
    enabled: runId !== null && runId > 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status === "success" || status === "failed" || status === "partial") return false
      return 2000 // 진행 중일 때 2초마다 폴링
    },
  })
}

export function useComplexLastRuns() {
  return useQuery({
    queryKey: ["complexLastRuns"],
    queryFn: () => complexesApi.getLastRuns(),
    refetchInterval: 10_000,
  })
}

// --- 일괄 지역 발견 ---

interface BatchDiscoverResult {
  regionCode: string
  regionName: string
  total_found: number
  new_registered: number
  already_exists: number
  error?: string
}

export interface BatchDiscoverProgress {
  status: "idle" | "running" | "completed" | "cancelled"
  totalRegions: number
  completedRegions: number
  currentRegion: string
  results: BatchDiscoverResult[]
  summary: {
    total_found: number
    new_registered: number
    already_exists: number
    failed: number
  }
}

const INITIAL_PROGRESS: BatchDiscoverProgress = {
  status: "idle",
  totalRegions: 0,
  completedRegions: 0,
  currentRegion: "",
  results: [],
  summary: { total_found: 0, new_registered: 0, already_exists: 0, failed: 0 },
}

export function useBatchDiscoverRegion() {
  const queryClient = useQueryClient()
  const [progress, setProgress] = useState<BatchDiscoverProgress>(INITIAL_PROGRESS)
  const abortRef = useRef<AbortController | null>(null)

  const start = useCallback(
    async (regions: { code: string; name: string }[]) => {
      const controller = new AbortController()
      abortRef.current = controller

      setProgress({
        status: "running",
        totalRegions: regions.length,
        completedRegions: 0,
        currentRegion: regions[0]?.name ?? "",
        results: [],
        summary: { total_found: 0, new_registered: 0, already_exists: 0, failed: 0 },
      })

      const results: BatchDiscoverResult[] = []
      const summary = { total_found: 0, new_registered: 0, already_exists: 0, failed: 0 }

      for (let i = 0; i < regions.length; i++) {
        if (controller.signal.aborted) break

        const region = regions[i]
        setProgress((prev) => ({ ...prev, currentRegion: region.name }))

        try {
          const result = await complexesApi.discoverRegion(region.code)
          summary.total_found += result.total_found
          summary.new_registered += result.new_registered
          summary.already_exists += result.already_exists
          results.push({
            regionCode: region.code,
            regionName: region.name,
            total_found: result.total_found,
            new_registered: result.new_registered,
            already_exists: result.already_exists,
          })
        } catch (err) {
          summary.failed++
          results.push({
            regionCode: region.code,
            regionName: region.name,
            total_found: 0,
            new_registered: 0,
            already_exists: 0,
            error: err instanceof Error ? err.message : "발견 실패",
          })
        }

        setProgress({
          status: controller.signal.aborted ? "cancelled" : "running",
          totalRegions: regions.length,
          completedRegions: i + 1,
          currentRegion: region.name,
          results: [...results],
          summary: { ...summary },
        })
      }

      setProgress((prev) => ({
        ...prev,
        status: controller.signal.aborted ? "cancelled" : "completed",
      }))

      queryClient.invalidateQueries({ queryKey: ["complexes"] })
    },
    [queryClient],
  )

  const cancel = useCallback(() => {
    abortRef.current?.abort()
  }, [])

  const reset = useCallback(() => {
    setProgress(INITIAL_PROGRESS)
  }, [])

  return { progress, start, cancel, reset }
}
