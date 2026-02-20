import { useQuery } from "@tanstack/react-query"
import { dataApi } from "@/api/data"

export function useKBPrices(params?: {
  complex_id?: number
  area_id?: number
  from_date?: string
  to_date?: string
  skip?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ["kb-prices", params],
    queryFn: () => dataApi.kbPrices(params),
    enabled: !!params?.complex_id,
  })
}

export function useTransactions(params?: {
  complex_id?: number
  from_date?: string
  to_date?: string
  skip?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ["transactions", params],
    queryFn: () => dataApi.transactions(params),
    enabled: !!params?.complex_id,
  })
}

export function useListings(params?: {
  complex_id?: number
  status?: string
  skip?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ["listings", params],
    queryFn: () => dataApi.listings(params),
    enabled: !!params?.complex_id,
  })
}
