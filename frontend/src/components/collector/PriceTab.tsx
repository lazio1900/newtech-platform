import React, { useState, useCallback, useMemo } from "react"
import { useKBPrices } from "@/hooks/useData"
import Pagination from "./Pagination"
import PriceTrendChart from "./PriceTrendChart"
import type { KBPrice } from "@/types/data"
import type { Area } from "@/types/complex"

interface PriceTabProps {
  complexId: number
  areas?: Area[]
}

const PAGE_SIZE = 30

const PriceTab: React.FC<PriceTabProps> = ({ complexId, areas = [] }) => {
  const [page, setPage] = useState(1)
  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(null)

  const { data, isLoading } = useKBPrices({
    complex_id: complexId,
    area_id: selectedAreaId ?? undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  })

  // Also fetch all for chart (up to 200 data points)
  const { data: allPrices } = useKBPrices({
    complex_id: complexId,
    area_id: selectedAreaId ?? undefined,
    limit: 200,
  })

  const prices: KBPrice[] = Array.isArray(data) ? data : (data as any)?.items ?? []
  const total: number = Array.isArray(data) ? prices.length : (data as any)?.total ?? prices.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const chartPrices: KBPrice[] = Array.isArray(allPrices)
    ? allPrices
    : (allPrices as any)?.items ?? []

  // area_id → Area 매핑
  const areaMap = useMemo(() => {
    const m: Record<number, Area> = {}
    for (const a of areas) {
      m[a.id] = a
    }
    return m
  }, [areas])

  const formatArea = (areaId: number) => {
    const area = areaMap[areaId]
    if (!area) return `#${areaId}`
    const pyeong = area.pyeong ? `${area.pyeong}평` : `${(area.exclusive_m2 / 3.3058).toFixed(0)}평`
    const supply = area.supply_m2 ? ` / 공급 ${area.supply_m2}㎡` : ""
    return `전용 ${area.exclusive_m2}㎡${supply} (${pyeong})`
  }

  const formatPrice = (v: number | null) => {
    if (v == null) return "-"
    if (v >= 10000) return `${(v / 10000).toFixed(1)}억`
    return `${v.toLocaleString()}만`
  }

  const handleAreaChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value
    setSelectedAreaId(val ? Number(val) : null)
    setPage(1)
  }

  const handleExportCSV = useCallback(() => {
    if (!chartPrices.length) return

    const headers = ["기준일", "전용면적(㎡)", "공급면적(㎡)", "평형", "일반가(만원)", "상위평균(만원)", "하위평균(만원)", "수집일"]
    const rows = chartPrices.map((p) => {
      const area = areaMap[p.area_id]
      return [
        p.as_of_date,
        area?.exclusive_m2 ?? "",
        area?.supply_m2 ?? "",
        area?.pyeong ?? "",
        p.general_price ?? "",
        p.high_avg_price ?? "",
        p.low_avg_price ?? "",
        p.fetched_at ? new Date(p.fetched_at).toLocaleDateString("ko-KR") : "",
      ]
    })

    const csvContent =
      "\uFEFF" + [headers.join(","), ...rows.map((r) => r.join(","))].join("\n")

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = `kb_prices_complex_${complexId}.csv`
    link.click()
    URL.revokeObjectURL(url)
  }, [chartPrices, complexId, areaMap])

  return (
    <div>
      {/* 면적 필터 */}
      {areas.length > 0 && (
        <div className="collector-toolbar" style={{ marginBottom: 12 }}>
          <div className="collector-toolbar-left" style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap" }}>면적 선택</label>
            <select
              className="collector-select"
              value={selectedAreaId ?? ""}
              onChange={handleAreaChange}
              style={{ minWidth: 200 }}
            >
              <option value="">전체 면적</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  전용 {a.exclusive_m2}㎡{a.supply_m2 ? ` / 공급 ${a.supply_m2}㎡` : ""}{a.pyeong ? ` (${a.pyeong}평)` : ` (${(a.exclusive_m2 / 3.3058).toFixed(0)}평)`}
                </option>
              ))}
            </select>
            {selectedAreaId && (
              <button
                className="collector-btn collector-btn-sm collector-btn-outline"
                onClick={() => { setSelectedAreaId(null); setPage(1) }}
              >
                초기화
              </button>
            )}
          </div>
        </div>
      )}

      {/* Chart */}
      <PriceTrendChart prices={chartPrices} areaMap={areaMap} />

      {/* Export */}
      <div className="collector-export-row">
        <button
          className="collector-btn collector-btn-outline"
          onClick={handleExportCSV}
          disabled={chartPrices.length === 0}
        >
          CSV 내보내기
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="collector-loading">
          <div className="spinner" />
          <p>시세 데이터 불러오는 중...</p>
        </div>
      ) : prices.length === 0 ? (
        <div className="collector-empty">KB 시세 데이터가 없습니다.</div>
      ) : (
        <>
          <div className="collector-table-wrapper">
            <table className="collector-table">
              <thead>
                <tr>
                  <th>기준일</th>
                  <th>면적 (전용/공급)</th>
                  <th>일반가</th>
                  <th>상위평균</th>
                  <th>하위평균</th>
                  <th>수집일</th>
                </tr>
              </thead>
              <tbody>
                {prices.map((p) => (
                  <tr key={p.id}>
                    <td className="center">{p.as_of_date}</td>
                    <td className="center">{formatArea(p.area_id)}</td>
                    <td className="right">{formatPrice(p.general_price)}</td>
                    <td className="right">{formatPrice(p.high_avg_price)}</td>
                    <td className="right">{formatPrice(p.low_avg_price)}</td>
                    <td className="center nowrap">
                      {p.fetched_at ? new Date(p.fetched_at).toLocaleDateString("ko-KR") : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination
            currentPage={page}
            totalPages={totalPages}
            onPageChange={setPage}
            totalItems={total}
          />
        </>
      )}
    </div>
  )
}

export default PriceTab
