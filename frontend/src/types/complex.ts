export type PriorityLevel = "high" | "normal" | "low"

export interface Area {
  id: number
  exclusive_m2: number
  supply_m2: number | null
  pyeong: number | null
  kb_area_code: string | null
}

export interface Complex {
  id: number
  name: string
  address: string
  region_code: string | null
  kb_complex_id: string | null
  priority: PriorityLevel
  is_active: boolean
  collect_listings: boolean
  total_households: number | null
  corridor_type: string | null
  build_year: number | null
  areas: Area[]
}

export interface ComplexCreate {
  name: string
  address: string
  region_code?: string
  kb_complex_id?: string
  priority?: PriorityLevel
  is_active?: boolean
  collect_listings?: boolean
}

export interface ComplexLastRun {
  run_id: number
  status: string
  started_at: string | null
  finished_at: string | null
}

export type ComplexLastRunMap = Record<number, ComplexLastRun>

export interface PaginatedComplexes {
  items: Complex[]
  total: number
}

export interface RegionCounts {
  sido_counts: Record<string, number>
  region_counts: Record<string, number>
}
