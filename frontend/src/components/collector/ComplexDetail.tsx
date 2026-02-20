import React, { useState, useMemo } from "react"
import { useComplex } from "@/hooks/useComplexes"
import { useKBPrices, useTransactions, useListings } from "@/hooks/useData"
import StatusBadge from "./StatusBadge"
import type { Area } from "@/types/complex"

interface ComplexDetailProps {
  complexId: number
  onBack: () => void
}

type SubTab = "areas" | "prices" | "transactions" | "listings"

const ComplexDetail: React.FC<ComplexDetailProps> = ({ complexId, onBack }) => {
  const [subTab, setSubTab] = useState<SubTab>("areas")
  const { data: complex, isLoading, isError } = useComplex(complexId)

  const { data: prices, isLoading: pricesLoading } = useKBPrices(
    subTab === "prices" ? { complex_id: complexId, limit: 50 } : undefined
  )
  const { data: transactions, isLoading: txLoading } = useTransactions(
    subTab === "transactions" ? { complex_id: complexId, limit: 50 } : undefined
  )
  const { data: listings, isLoading: listingsLoading } = useListings(
    subTab === "listings" ? { complex_id: complexId, limit: 50 } : undefined
  )

  const areaMap = useMemo(() => {
    const m: Record<number, Area> = {}
    for (const a of complex?.areas ?? []) {
      m[a.id] = a
    }
    return m
  }, [complex?.areas])

  if (isLoading) {
    return (
      <div className="collector-loading">
        <div className="spinner" />
        <p>불러오는 중...</p>
      </div>
    )
  }

  if (isError || !complex) {
    return (
      <div className="collector-error">
        <p>단지 정보를 불러올 수 없습니다.</p>
        <button className="collector-btn collector-btn-outline" onClick={onBack}>
          목록으로
        </button>
      </div>
    )
  }

  const formatM2 = (v: number | null) => (v != null ? `${v}m²` : "-")
  const formatPyeong = (v: number | null) => (v != null ? `${v}평` : "-")
  const formatPrice = (v: number | null) => {
    if (v == null) return "-"
    if (v >= 10000) return `${(v / 10000).toFixed(1)}억`
    return `${v.toLocaleString()}만`
  }

  const formatArea = (areaId: number) => {
    const area = areaMap[areaId]
    if (!area) return `#${areaId}`
    const pyeong = area.pyeong ? `${area.pyeong}평` : `${(area.exclusive_m2 / 3.3058).toFixed(0)}평`
    const supply = area.supply_m2 ? ` / 공급 ${area.supply_m2}㎡` : ""
    return `전용 ${area.exclusive_m2}㎡${supply} (${pyeong})`
  }

  const tabs: { key: SubTab; label: string }[] = [
    { key: "areas", label: "면적" },
    { key: "prices", label: "시세" },
    { key: "transactions", label: "거래" },
    { key: "listings", label: "매물" },
  ]

  return (
    <div>
      <div className="collector-back-row">
        <button className="collector-back-btn" onClick={onBack}>
          &larr; 목록으로
        </button>
      </div>

      <div className="collector-card">
        <div className="collector-card-header">
          <h3>{complex.name}</h3>
          <StatusBadge status={complex.is_active ? "active" : "disabled"} />
        </div>

        <div className="collector-info-grid">
          <div className="collector-info-item">
            <span className="collector-info-label">ID</span>
            <span className="collector-info-value">{complex.id}</span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">주소</span>
            <span className="collector-info-value">{complex.address}</span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">지역코드</span>
            <span className="collector-info-value">{complex.region_code ?? "-"}</span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">KB 단지 ID</span>
            <span className="collector-info-value">{complex.kb_complex_id ?? "-"}</span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">우선순위</span>
            <span className="collector-info-value">
              {complex.priority === "high" ? "높음" : complex.priority === "low" ? "낮음" : "보통"}
            </span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">매물 수집</span>
            <span className="collector-info-value">
              {complex.collect_listings ? "포함" : "미포함"}
            </span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">세대수</span>
            <span className="collector-info-value">
              {complex.total_households ? `${complex.total_households.toLocaleString()}세대` : "-"}
            </span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">복도타입</span>
            <span className="collector-info-value">{complex.corridor_type ?? "-"}</span>
          </div>
          <div className="collector-info-item">
            <span className="collector-info-label">연식</span>
            <span className="collector-info-value">
              {complex.build_year
                ? `${new Date().getFullYear() - complex.build_year}년 (${complex.build_year}년 준공)`
                : "-"}
            </span>
          </div>
        </div>

        <div className="collector-subtabs">
          {tabs.map((t) => (
            <button
              key={t.key}
              className={`collector-subtab ${subTab === t.key ? "active" : ""}`}
              onClick={() => setSubTab(t.key)}
            >
              {t.label}
              {t.key === "areas" && ` (${complex.areas?.length ?? 0})`}
            </button>
          ))}
        </div>

        {/* Areas tab */}
        {subTab === "areas" && (
          <div className="collector-table-wrapper">
            {complex.areas && complex.areas.length > 0 ? (
              <table className="collector-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>전용면적</th>
                    <th>공급면적</th>
                    <th>평수</th>
                    <th>KB 면적코드</th>
                  </tr>
                </thead>
                <tbody>
                  {complex.areas.map((area: Area) => (
                    <tr key={area.id}>
                      <td className="center">{area.id}</td>
                      <td className="center">{formatM2(area.exclusive_m2)}</td>
                      <td className="center">{formatM2(area.supply_m2)}</td>
                      <td className="center">{formatPyeong(area.pyeong)}</td>
                      <td className="center">{area.kb_area_code ?? "-"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="collector-empty">등록된 면적 정보가 없습니다.</div>
            )}
          </div>
        )}

        {/* Prices tab */}
        {subTab === "prices" && (
          <div className="collector-table-wrapper">
            {pricesLoading ? (
              <div className="collector-loading">
                <div className="spinner" />
                <p>시세 데이터 불러오는 중...</p>
              </div>
            ) : prices && prices.length > 0 ? (
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
            ) : (
              <div className="collector-empty">시세 데이터가 없습니다.</div>
            )}
          </div>
        )}

        {/* Transactions tab */}
        {subTab === "transactions" && (
          <div className="collector-table-wrapper">
            {txLoading ? (
              <div className="collector-loading">
                <div className="spinner" />
                <p>거래 데이터 불러오는 중...</p>
              </div>
            ) : transactions && transactions.length > 0 ? (
              <table className="collector-table">
                <thead>
                  <tr>
                    <th>계약일</th>
                    <th>가격</th>
                    <th>전용면적</th>
                    <th>층</th>
                    <th>출처</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((t) => (
                    <tr key={t.id}>
                      <td className="center">{t.contract_date}</td>
                      <td className="right">{formatPrice(t.price)}</td>
                      <td className="center">{t.exclusive_m2}m2</td>
                      <td className="center">{t.floor ?? "-"}</td>
                      <td className="center">{t.source}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="collector-empty">거래 데이터가 없습니다.</div>
            )}
          </div>
        )}

        {/* Listings tab */}
        {subTab === "listings" && (
          <div className="collector-table-wrapper">
            {listingsLoading ? (
              <div className="collector-loading">
                <div className="spinner" />
                <p>매물 데이터 불러오는 중...</p>
              </div>
            ) : listings && listings.length > 0 ? (
              <table className="collector-table">
                <thead>
                  <tr>
                    <th>매물 ID</th>
                    <th>호가</th>
                    <th>전용면적</th>
                    <th>층</th>
                    <th>상태</th>
                    <th>수집일</th>
                  </tr>
                </thead>
                <tbody>
                  {listings.map((l) => (
                    <tr key={l.id}>
                      <td className="center">{l.source_listing_id}</td>
                      <td className="right">{formatPrice(l.ask_price)}</td>
                      <td className="center">{l.exclusive_m2 != null ? `${l.exclusive_m2}m2` : "-"}</td>
                      <td className="center">{l.floor ?? "-"}</td>
                      <td className="center">
                        <StatusBadge status={l.status} />
                      </td>
                      <td className="center nowrap">
                        {l.fetched_at ? new Date(l.fetched_at).toLocaleDateString("ko-KR") : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="collector-empty">매물 데이터가 없습니다.</div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default ComplexDetail
