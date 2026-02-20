import React, { useState, useCallback } from "react"
import { useComplexes, useCollectComplex, useComplexLastRuns, useDiscoverRegion, useBatchDiscoverRegion, useSigunguList, useRunStatus } from "@/hooks/useComplexes"
import StatusBadge from "./StatusBadge"
import Pagination from "./Pagination"
import ComplexFormModal from "./ComplexFormModal"
import type { Complex } from "@/types/complex"

interface ComplexListProps {
  onSelectComplex: (id: number) => void
}

const SIDO_LIST = [
  { code: "11", name: "서울" }, { code: "26", name: "부산" }, { code: "27", name: "대구" },
  { code: "28", name: "인천" }, { code: "29", name: "광주" }, { code: "30", name: "대전" },
  { code: "31", name: "울산" }, { code: "36", name: "세종" }, { code: "41", name: "경기" },
  { code: "42", name: "강원" }, { code: "43", name: "충북" }, { code: "44", name: "충남" },
  { code: "45", name: "전북" }, { code: "46", name: "전남" }, { code: "47", name: "경북" },
  { code: "48", name: "경남" }, { code: "50", name: "제주" },
]

const PAGE_SIZE = 20

const ComplexList: React.FC<ComplexListProps> = ({ onSelectComplex }) => {
  const [search, setSearch] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [page, setPage] = useState(1)
  const [showModal, setShowModal] = useState(false)
  const [showDiscoverModal, setShowDiscoverModal] = useState(false)
  const [editComplex, setEditComplex] = useState<Complex | null>(null)
  const [selectedSido, setSelectedSido] = useState("")
  const [discoverCode, setDiscoverCode] = useState("")
  const [selectedSigungus, setSelectedSigungus] = useState<Set<string>>(new Set())
  const [activeRunId, setActiveRunId] = useState<number | null>(null)
  const [discoverResult, setDiscoverResult] = useState<{
    total_found: number; new_registered: number; already_exists: number
  } | null>(null)

  const { data, isLoading, isError } = useComplexes({
    search: debouncedSearch || undefined,
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
  })
  const { data: lastRuns } = useComplexLastRuns()
  const collectMutation = useCollectComplex()
  const discoverMutation = useDiscoverRegion()
  const { progress: batchProgress, start: startBatchDiscover, cancel: cancelBatchDiscover, reset: resetBatchDiscover } = useBatchDiscoverRegion()
  const { data: sigunguList, isLoading: sigunguLoading } = useSigunguList(selectedSido)
  const { data: runStatus } = useRunStatus(activeRunId)

  const debounceRef = React.useRef<ReturnType<typeof setTimeout>>(undefined)

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setDebouncedSearch(value)
      setPage(1)
    }, 400)
  }, [])

  const handleCollect = (e: React.MouseEvent, complexId: number) => {
    e.stopPropagation()
    collectMutation.mutate(complexId, {
      onSuccess: (data) => {
        setActiveRunId(data.run_id)
      },
    })
  }

  const handleEdit = (e: React.MouseEvent, complex: Complex) => {
    e.stopPropagation()
    setEditComplex(complex)
    setShowModal(true)
  }

  const handleCreate = () => {
    setEditComplex(null)
    setShowModal(true)
  }

  const handleCloseModal = () => {
    setShowModal(false)
    setEditComplex(null)
  }

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const priorityLabel = (p: string) => {
    if (p === "high") return "높음"
    if (p === "low") return "낮음"
    return "보통"
  }

  return (
    <div>
      <div className="collector-toolbar">
        <div className="collector-toolbar-left">
          <input
            className="collector-search-input"
            type="text"
            placeholder="단지명 또는 주소로 검색..."
            value={search}
            onChange={(e) => handleSearchChange(e.target.value)}
          />
        </div>
        <div className="collector-toolbar-right">
          <button
            className="collector-btn collector-btn-outline"
            onClick={() => { setShowDiscoverModal(true); setDiscoverResult(null); setDiscoverCode(""); setSelectedSido(""); setSelectedSigungus(new Set()); resetBatchDiscover(); }}
          >
            지역 발견
          </button>
          <button className="collector-btn collector-btn-primary" onClick={handleCreate}>
            + 단지 등록
          </button>
        </div>
      </div>

      {/* 수집 진행 상태 배너 */}
      {activeRunId && runStatus && (
        <div style={{
          marginBottom: 16, padding: 16, borderRadius: 8,
          border: `1px solid ${runStatus.status === "running" || runStatus.status === "pending" ? "#006FBD" : runStatus.status === "success" ? "#20c997" : runStatus.status === "partial" ? "#FF8C00" : "#EF5350"}`,
          backgroundColor: runStatus.status === "running" || runStatus.status === "pending" ? "#f0f6ff" : runStatus.status === "success" ? "#f0f9f4" : runStatus.status === "partial" ? "#fff8f0" : "#fff5f5",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {(runStatus.status === "running" || runStatus.status === "pending") && (
                <div className="spinner" style={{ width: 16, height: 16 }} />
              )}
              <strong style={{ fontSize: 14 }}>
                {runStatus.status === "pending" && "수집 준비 중..."}
                {runStatus.status === "running" && "수집 진행 중..."}
                {runStatus.status === "success" && "수집 완료"}
                {runStatus.status === "partial" && "수집 부분 완료"}
                {runStatus.status === "failed" && "수집 실패"}
              </strong>
            </div>
            {(runStatus.status === "success" || runStatus.status === "failed" || runStatus.status === "partial") && (
              <button
                className="collector-btn collector-btn-sm collector-btn-outline"
                onClick={() => setActiveRunId(null)}
                style={{ fontSize: 12 }}
              >
                닫기
              </button>
            )}
          </div>

          {runStatus.total_tasks > 0 && (
            <>
              <div style={{
                height: 6, backgroundColor: "#e0e0e0", borderRadius: 3,
                overflow: "hidden", marginBottom: 8,
              }}>
                <div style={{
                  height: "100%", borderRadius: 3, transition: "width 0.3s",
                  width: `${Math.round(((runStatus.success_count + runStatus.failed_count) / runStatus.total_tasks) * 100)}%`,
                  backgroundColor: runStatus.failed_count > 0 ? "#FF8C00" : "#006FBD",
                }} />
              </div>
              <div style={{ fontSize: 12, color: "#666", display: "flex", gap: 16 }}>
                <span>전체: {runStatus.total_tasks}건</span>
                <span style={{ color: "#20c997" }}>성공: {runStatus.success_count}건</span>
                {runStatus.failed_count > 0 && (
                  <span style={{ color: "#EF5350" }}>실패: {runStatus.failed_count}건</span>
                )}
              </div>

              {/* 개별 태스크 상태 */}
              {runStatus.tasks.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, maxHeight: 120, overflowY: "auto" }}>
                  {runStatus.tasks.map((t, i) => (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, padding: "2px 0" }}>
                      <span style={{
                        width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                        backgroundColor: t.status === "success" ? "#20c997" : t.status === "failed" ? "#EF5350" : t.status === "running" ? "#006FBD" : "#ccc",
                      }} />
                      <span style={{ color: "#333" }}>{t.task_key}</span>
                      {t.status === "success" && <span style={{ color: "#999" }}>({t.items_saved}건 저장)</span>}
                      {t.status === "failed" && <span style={{ color: "#EF5350" }}>{t.error_message?.slice(0, 60)}</span>}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {isError && (
        <div className="collector-error">
          <p>데이터를 불러오는 중 오류가 발생했습니다.</p>
        </div>
      )}

      {isLoading ? (
        <div className="collector-loading">
          <div className="spinner" />
          <p>불러오는 중...</p>
        </div>
      ) : items.length === 0 ? (
        <div className="collector-empty">
          {debouncedSearch
            ? `"${debouncedSearch}" 검색 결과가 없습니다.`
            : "등록된 단지가 없습니다."}
        </div>
      ) : (
        <>
          <div className="collector-table-wrapper">
            <table className="collector-table">
              <thead>
                <tr>
                  <th style={{ width: 60 }}>ID</th>
                  <th>단지명</th>
                  <th>주소</th>
                  <th style={{ width: 110 }}>지역코드</th>
                  <th style={{ width: 70 }}>우선순위</th>
                  <th style={{ width: 70 }}>상태</th>
                  <th style={{ width: 80 }}>최근 수집</th>
                  <th style={{ width: 140 }}>액션</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => {
                  const lastRun = lastRuns?.[c.id]
                  return (
                    <tr
                      key={c.id}
                      className="clickable"
                      onClick={() => onSelectComplex(c.id)}
                    >
                      <td className="center">{c.id}</td>
                      <td>{c.name}</td>
                      <td>{c.address}</td>
                      <td className="center">{c.region_code ?? "-"}</td>
                      <td className="center">
                        <span className={`priority-${c.priority}`}>
                          {priorityLabel(c.priority)}
                        </span>
                      </td>
                      <td className="center">
                        <StatusBadge status={c.is_active ? "active" : "disabled"} />
                      </td>
                      <td className="center">
                        {lastRun ? (
                          <StatusBadge status={lastRun.status} />
                        ) : (
                          <span style={{ color: "#999", fontSize: 12 }}>-</span>
                        )}
                      </td>
                      <td className="center">
                        <div className="collector-btn-group" style={{ justifyContent: "center" }}>
                          <button
                            className="collector-btn collector-btn-sm collector-btn-primary"
                            onClick={(e) => handleCollect(e, c.id)}
                            disabled={collectMutation.isPending}
                          >
                            수집
                          </button>
                          <button
                            className="collector-btn collector-btn-sm collector-btn-outline"
                            onClick={(e) => handleEdit(e, c)}
                          >
                            수정
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
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

      {showModal && (
        <ComplexFormModal complex={editComplex} onClose={handleCloseModal} />
      )}

      {showDiscoverModal && (
        <div className="collector-modal-overlay" onClick={() => setShowDiscoverModal(false)}>
          <div className="collector-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="collector-modal-header">
              <h3>지역 발견</h3>
              <button className="collector-modal-close" onClick={() => setShowDiscoverModal(false)}>&times;</button>
            </div>
            <div className="collector-modal-body">
              <p style={{ fontSize: 13, color: "#666", marginBottom: 16 }}>
                시/도 → 시/군/구를 선택하거나, 지역코드를 직접 입력하여 KB부동산에서 아파트 단지를 자동 발견합니다.
              </p>

              <div className="collector-form-group">
                <label>1단계: 시/도 선택</label>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                  {SIDO_LIST.map((s) => (
                    <button
                      key={s.code}
                      className={`collector-btn collector-btn-sm ${selectedSido === s.code ? "collector-btn-primary" : "collector-btn-outline"}`}
                      onClick={() => {
                        setSelectedSido(s.code)
                        setSelectedSigungus(new Set())
                        setDiscoverCode("")
                        setDiscoverResult(null)
                        resetBatchDiscover()
                      }}
                    >
                      {s.name}
                    </button>
                  ))}
                </div>
              </div>

              {selectedSido && (
                <div className="collector-form-group">
                  <label>2단계: 시/군/구 선택</label>
                  {sigunguLoading ? (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
                      <div className="spinner" style={{ width: 16, height: 16 }} />
                      <span style={{ fontSize: 13, color: "#666" }}>시군구 목록 불러오는 중...</span>
                    </div>
                  ) : sigunguList && sigunguList.length > 0 ? (
                    <>
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
                        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={selectedSigungus.size === sigunguList.length}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedSigungus(new Set(sigunguList.map((sg) => sg.code)))
                              } else {
                                setSelectedSigungus(new Set())
                              }
                            }}
                            disabled={batchProgress.status === "running"}
                          />
                          전체 선택 ({sigunguList.length}개)
                        </label>
                        {selectedSigungus.size > 0 && selectedSigungus.size < sigunguList.length && (
                          <span style={{ fontSize: 12, color: "#666" }}>{selectedSigungus.size}개 선택됨</span>
                        )}
                      </div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                        {sigunguList.map((sg) => (
                          <button
                            key={sg.code}
                            className={`collector-btn collector-btn-sm ${selectedSigungus.has(sg.code) ? "collector-btn-primary" : "collector-btn-outline"}`}
                            disabled={batchProgress.status === "running"}
                            onClick={() => {
                              setSelectedSigungus((prev) => {
                                const next = new Set(prev)
                                if (next.has(sg.code)) next.delete(sg.code)
                                else next.add(sg.code)
                                return next
                              })
                            }}
                          >
                            {sg.name}
                          </button>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p style={{ fontSize: 13, color: "#999", padding: "8px 0" }}>
                      시군구 목록을 불러올 수 없습니다. 아래에서 지역코드를 직접 입력해주세요.
                    </p>
                  )}
                </div>
              )}

              <div className="collector-form-group">
                <label>직접 입력 (단일 발견)</label>
                <input
                  className="collector-input"
                  type="text"
                  placeholder="예: 11680 (강남구), 1168010100 (역삼동)"
                  value={discoverCode}
                  onChange={(e) => setDiscoverCode(e.target.value)}
                  disabled={batchProgress.status === "running"}
                />
              </div>

              {/* 단일 발견 로딩/에러/결과 */}
              {discoverMutation.isPending && (
                <div className="collector-loading" style={{ padding: "20px 0" }}>
                  <div className="spinner" />
                  <p>KB부동산에서 단지를 검색하고 있습니다...</p>
                </div>
              )}

              {discoverMutation.isError && (
                <div className="collector-error" style={{ marginTop: 12 }}>
                  <p>발견 중 오류가 발생했습니다. 지역코드를 확인해주세요.</p>
                </div>
              )}

              {discoverResult && (
                <div style={{
                  marginTop: 16, padding: 16, backgroundColor: "#f0f9f4",
                  borderRadius: 8, border: "1px solid #20c997"
                }}>
                  <p style={{ fontWeight: 700, marginBottom: 8, color: "#2E7D32" }}>발견 완료</p>
                  <div style={{ display: "flex", gap: 24 }}>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>총 발견</span>
                      <p style={{ fontSize: 20, fontWeight: 700 }}>{discoverResult.total_found}개</p>
                    </div>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>신규 등록</span>
                      <p style={{ fontSize: 20, fontWeight: 700, color: "#006FBD" }}>{discoverResult.new_registered}개</p>
                    </div>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>이미 존재</span>
                      <p style={{ fontSize: 20, fontWeight: 700, color: "#999" }}>{discoverResult.already_exists}개</p>
                    </div>
                  </div>
                </div>
              )}

              {/* 배치 발견 진행률 */}
              {batchProgress.status === "running" && (
                <div style={{ marginTop: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 }}>
                    <span>{batchProgress.currentRegion} 발견 중...</span>
                    <span>{batchProgress.completedRegions}/{batchProgress.totalRegions}</span>
                  </div>
                  <div style={{ height: 8, backgroundColor: "#e0e0e0", borderRadius: 4, overflow: "hidden", marginBottom: 12 }}>
                    <div style={{
                      height: "100%", borderRadius: 4, transition: "width 0.3s",
                      width: `${Math.round((batchProgress.completedRegions / batchProgress.totalRegions) * 100)}%`,
                      backgroundColor: "#006FBD",
                    }} />
                  </div>
                  <div style={{ display: "flex", gap: 20, marginBottom: 12, fontSize: 13 }}>
                    <div>총 발견: <strong>{batchProgress.summary.total_found}</strong></div>
                    <div>신규: <strong style={{ color: "#006FBD" }}>{batchProgress.summary.new_registered}</strong></div>
                    <div>기존: <strong style={{ color: "#999" }}>{batchProgress.summary.already_exists}</strong></div>
                    {batchProgress.summary.failed > 0 && (
                      <div>실패: <strong style={{ color: "#EF5350" }}>{batchProgress.summary.failed}</strong></div>
                    )}
                  </div>
                  <div style={{ maxHeight: 140, overflowY: "auto", fontSize: 12 }}>
                    {batchProgress.results.map((r, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 0" }}>
                        <span style={{
                          width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                          backgroundColor: r.error ? "#EF5350" : "#20c997",
                        }} />
                        <span>{r.regionName}</span>
                        {r.error ? (
                          <span style={{ color: "#EF5350" }}>{r.error}</span>
                        ) : (
                          <span style={{ color: "#999" }}>발견 {r.total_found} / 신규 {r.new_registered}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 배치 발견 완료/취소 결과 */}
              {(batchProgress.status === "completed" || batchProgress.status === "cancelled") && (
                <div style={{
                  marginTop: 16, padding: 16, borderRadius: 8,
                  backgroundColor: batchProgress.status === "completed" ? "#f0f9f4" : "#fff8f0",
                  border: `1px solid ${batchProgress.status === "completed" ? "#20c997" : "#FF8C00"}`,
                }}>
                  <p style={{ fontWeight: 700, marginBottom: 8, color: batchProgress.status === "completed" ? "#2E7D32" : "#E65100" }}>
                    {batchProgress.status === "completed" ? "일괄 발견 완료" : `발견 취소 (${batchProgress.completedRegions}/${batchProgress.totalRegions} 처리)`}
                  </p>
                  <div style={{ display: "flex", gap: 24 }}>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>총 발견</span>
                      <p style={{ fontSize: 20, fontWeight: 700 }}>{batchProgress.summary.total_found}개</p>
                    </div>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>신규 등록</span>
                      <p style={{ fontSize: 20, fontWeight: 700, color: "#006FBD" }}>{batchProgress.summary.new_registered}개</p>
                    </div>
                    <div>
                      <span style={{ fontSize: 12, color: "#666" }}>이미 존재</span>
                      <p style={{ fontSize: 20, fontWeight: 700, color: "#999" }}>{batchProgress.summary.already_exists}개</p>
                    </div>
                    {batchProgress.summary.failed > 0 && (
                      <div>
                        <span style={{ fontSize: 12, color: "#666" }}>실패</span>
                        <p style={{ fontSize: 20, fontWeight: 700, color: "#EF5350" }}>{batchProgress.summary.failed}개</p>
                      </div>
                    )}
                  </div>
                  {batchProgress.results.length > 0 && (
                    <div style={{ marginTop: 12, maxHeight: 140, overflowY: "auto", fontSize: 12 }}>
                      {batchProgress.results.map((r, i) => (
                        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "3px 0" }}>
                          <span style={{
                            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
                            backgroundColor: r.error ? "#EF5350" : "#20c997",
                          }} />
                          <span>{r.regionName}</span>
                          {r.error ? (
                            <span style={{ color: "#EF5350" }}>{r.error}</span>
                          ) : (
                            <span style={{ color: "#999" }}>발견 {r.total_found} / 신규 {r.new_registered}</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="collector-modal-footer">
              <button
                className="collector-btn collector-btn-outline"
                onClick={() => {
                  if (batchProgress.status === "running") {
                    cancelBatchDiscover()
                  } else {
                    setShowDiscoverModal(false)
                    resetBatchDiscover()
                  }
                }}
              >
                {batchProgress.status === "running" ? "취소" : "닫기"}
              </button>
              {selectedSigungus.size > 1 ? (
                <button
                  className="collector-btn collector-btn-primary"
                  disabled={batchProgress.status === "running"}
                  onClick={() => {
                    setDiscoverResult(null)
                    resetBatchDiscover()
                    const regions = (sigunguList ?? [])
                      .filter((sg) => selectedSigungus.has(sg.code))
                      .map((sg) => ({ code: sg.code, name: sg.name }))
                    startBatchDiscover(regions)
                  }}
                >
                  {batchProgress.status === "running"
                    ? `발견 중... (${batchProgress.completedRegions}/${batchProgress.totalRegions})`
                    : `${selectedSigungus.size}개 지역 일괄 발견`}
                </button>
              ) : (
                <button
                  className="collector-btn collector-btn-primary"
                  disabled={
                    (selectedSigungus.size === 0 && !discoverCode.trim()) ||
                    discoverMutation.isPending ||
                    batchProgress.status === "running"
                  }
                  onClick={() => {
                    setDiscoverResult(null)
                    const code = selectedSigungus.size === 1
                      ? [...selectedSigungus][0]
                      : discoverCode.trim()
                    discoverMutation.mutate(code, {
                      onSuccess: (result) => setDiscoverResult(result),
                    })
                  }}
                >
                  {discoverMutation.isPending ? "검색 중..." : "발견 시작"}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ComplexList
