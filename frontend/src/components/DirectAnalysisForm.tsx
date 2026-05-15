/**
 * Auditor 직접조회 폼 — customer 의 apply 폼과 동일 흐름(시도/시군구/단지/평형/동·호/등기부) +
 * 분석 조건 입력 → onAnalyze 콜백으로 결과 반환.
 *
 * NOTE: customer 의 apply 폼과 의도적으로 코드를 중복 유지. 양쪽 흐름이 안정화되면 추후
 * 공용 컴포넌트로 추출.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { complexesApi } from '../api/complexes';
import { regionsApi, RegionItem, DongItem } from '../api/regions';
import { registryApi } from '../api/registry';
import type { Area, Complex } from '@/types/complex';
import './DirectAnalysisForm.css';

const M2_PER_PYEONG = 3.3058;

export interface DirectAnalyzePayload {
  company: string;
  address: string;
  loanAmount: number;
  interestRate: number;
  duration: number;
  options: {
    complex_id?: number | null;
    area_id?: number | null;
    complex_name?: string | null;
    pyeong?: number | null;
    registry_ic_id?: number | null;
  };
}

interface DirectAnalysisFormProps {
  onAnalyze: (payload: DirectAnalyzePayload) => void;
  loading: boolean;
}

export default function DirectAnalysisForm({ onAnalyze, loading }: DirectAnalysisFormProps) {
  // 시도/시군구/읍면동
  const [sidoList, setSidoList] = useState<RegionItem[]>([]);
  const [sigunguList, setSigunguList] = useState<RegionItem[]>([]);
  const [dongList, setDongList] = useState<DongItem[]>([]);
  const [selectedSido, setSelectedSido] = useState<RegionItem | null>(null);
  const [selectedSigungu, setSelectedSigungu] = useState<RegionItem | null>(null);
  const [selectedDong, setSelectedDong] = useState<DongItem | null>(null);

  // 단지
  const [complexQuery, setComplexQuery] = useState<string>('');
  const [complexResults, setComplexResults] = useState<Complex[]>([]);
  const [complexTotal, setComplexTotal] = useState<number>(0);
  const [complexLoading, setComplexLoading] = useState<boolean>(false);
  const [selectedComplex, setSelectedComplex] = useState<Complex | null>(null);
  const [dongFilterFallback, setDongFilterFallback] = useState<boolean>(false);

  // 평형
  const [areas, setAreas] = useState<Area[]>([]);
  const [selectedArea, setSelectedArea] = useState<Area | null>(null);

  // 동·호
  const [dong, setDong] = useState<string>('');
  const [ho, setHo] = useState<string>('');

  // 등기부등본 발급
  const [registryLoading, setRegistryLoading] = useState<boolean>(false);
  const [registryResult, setRegistryResult] = useState<{
    status?: string; ic_id?: number | null; pdf_url?: string | null;
    cached?: boolean; error?: string | null;
  } | null>(null);
  // 등기부 표제부에서 추출된 전용면적 (자동 평형 제안용)
  const [registryExclusiveM2, setRegistryExclusiveM2] = useState<number | null>(null);

  // 업체명 + 대출 조건
  const [company, setCompany] = useState<string>('직접조회');
  const [amount, setAmount] = useState<string>('');
  const [interestRate, setInterestRate] = useState<string>('7.5');
  const [duration, setDuration] = useState<string>('12');

  const debounceRef = useRef<number | null>(null);

  // 시도 목록 로드
  useEffect(() => {
    regionsApi.listSido().then(setSidoList).catch(() => setSidoList([]));
  }, []);

  // 시도 → 시군구
  useEffect(() => {
    if (!selectedSido) {
      setSigunguList([]);
      setSelectedSigungu(null);
      return;
    }
    regionsApi.listSigungu(selectedSido.code).then(setSigunguList).catch(() => setSigunguList([]));
    setSelectedSigungu(null);
    setSelectedDong(null);
    setDongList([]);
    resetComplexAndDownstream();
  }, [selectedSido]);

  // 시군구 → 읍면동 + 단지 검색
  useEffect(() => {
    setSelectedDong(null);
    resetComplexAndDownstream();
    if (!selectedSigungu) {
      setDongList([]);
      return;
    }
    regionsApi.listEupmyeondong(selectedSigungu.code).then(setDongList).catch(() => setDongList([]));
    runComplexSearch(complexQuery);
  }, [selectedSigungu]);

  // 동 선택 → 단지 검색 다시
  useEffect(() => {
    if (!selectedSigungu) return;
    setSelectedComplex(null);
    runComplexSearch(complexQuery);
  }, [selectedDong]);

  // 검색어 디바운스
  useEffect(() => {
    if (!selectedSigungu) return;
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      runComplexSearch(complexQuery);
    }, 200);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [complexQuery]);

  // 단지 → 평형 로드
  useEffect(() => {
    if (!selectedComplex) {
      setAreas([]);
      setSelectedArea(null);
      return;
    }
    let cancelled = false;
    complexesApi.listAreas(selectedComplex.id)
      .then((data) => {
        if (cancelled) return;
        setAreas(data);
        setSelectedArea(data.length === 1 ? data[0] : null);
      })
      .catch(() => {
        if (!cancelled) { setAreas([]); setSelectedArea(null); }
      });
    return () => { cancelled = true; };
  }, [selectedComplex]);

  const resetComplexAndDownstream = () => {
    setSelectedComplex(null);
    setComplexResults([]);
    setComplexQuery('');
    setAreas([]);
    setSelectedArea(null);
    setDong('');
    setHo('');
    setRegistryResult(null);
    setRegistryExclusiveM2(null);
  };

  /** 등기부 발급 완료 후 표제부 면적 추출 + 가장 가까운 평형 자동 선택. */
  const applyAreaSuggestion = async (icId: number, complexId: number) => {
    try {
      const suggestion = await registryApi.getAreaSuggestion(icId, complexId);
      if (suggestion.exclusive_m2 != null) {
        setRegistryExclusiveM2(suggestion.exclusive_m2);
      }
      if (suggestion.suggested_area_id != null) {
        const next = areas.find((a) => a.id === suggestion.suggested_area_id);
        if (next) setSelectedArea(next);
      }
    } catch {
      // 추출 실패는 silent — 사용자가 직접 평형 선택 가능
    }
  };

  const runComplexSearch = async (query: string) => {
    if (!selectedSigungu) return;
    setComplexLoading(true);
    setDongFilterFallback(false);
    try {
      const baseParams = {
        region_code: selectedSigungu.code,
        search: query.trim() || undefined,
        limit: 50,
      };
      let res = await complexesApi.list({
        ...baseParams,
        dong_code: selectedDong?.code || undefined,
      });
      if (selectedDong && res.total === 0) {
        const fb = await complexesApi.list(baseParams);
        if (fb.total > 0) {
          setDongFilterFallback(true);
          res = fb;
        }
      }
      setComplexResults(res.items);
      setComplexTotal(res.total);
    } catch {
      setComplexResults([]);
      setComplexTotal(0);
    } finally {
      setComplexLoading(false);
    }
  };

  const derivedPyeong = useMemo<number | null>(() => {
    if (!selectedArea?.exclusive_m2) return null;
    return selectedArea.pyeong
      ? Math.round(selectedArea.pyeong)
      : Math.round(selectedArea.exclusive_m2 / M2_PER_PYEONG);
  }, [selectedArea]);

  const formatDongHo = (d: string, h: string): string => {
    const parts: string[] = [];
    if (d.trim()) parts.push(`${d.trim()}동`);
    if (h.trim()) parts.push(`${h.trim()}호`);
    return parts.join(' ');
  };

  const handleFetchRegistry = async () => {
    if (!selectedComplex || !dong.trim() || !ho.trim()) return;
    setRegistryLoading(true);
    setRegistryResult(null);
    setRegistryExclusiveM2(null);
    try {
      const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
      const fullAddress = `${roadAddr} ${selectedComplex.name}`.trim();
      const res = await registryApi.request({
        address: fullAddress, dong: dong.trim(), ho: ho.trim(),
        type: '집합건물', complex_id: selectedComplex.id,
      });
      if (res.status === 'completed' && res.ic_id) {
        setRegistryResult({
          status: res.status, ic_id: res.ic_id,
          pdf_url: registryApi.pdfUrl(res.ic_id),
          cached: res.cached, error: res.error_message,
        });
        applyAreaSuggestion(res.ic_id, selectedComplex.id);
        return;
      }
      const icId = res.ic_id;
      if (!icId) {
        setRegistryResult({ status: res.status, error: res.error_message || '발급 ID 미발급' });
        return;
      }
      setRegistryResult({ status: 'issuing', ic_id: icId });

      const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
      let elapsed = 0;
      while (elapsed < 180_000) {
        await sleep(5000);
        elapsed += 5000;
        try {
          const cur = await registryApi.get(icId);
          if (cur.status === 'completed') {
            setRegistryResult({
              status: 'completed', ic_id: icId,
              pdf_url: registryApi.pdfUrl(icId),
              cached: cur.cached, error: null,
            });
            applyAreaSuggestion(icId, selectedComplex.id);
            return;
          }
          if (cur.status === 'failed') {
            setRegistryResult({ status: 'failed', ic_id: icId, error: cur.error_message || '발급 실패' });
            return;
          }
          setRegistryResult({ status: cur.status, ic_id: icId });
        } catch { /* 일시 오류면 다음 폴링 */ }
      }
      setRegistryResult({
        status: 'timeout', ic_id: icId,
        error: '발급이 3분 안에 완료되지 않았습니다. 잠시 후 다시 확인해주세요.',
      });
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setRegistryResult({
        error: err?.response?.data?.detail || err?.message || '등기부등본 발급 요청에 실패했습니다',
      });
    } finally {
      setRegistryLoading(false);
    }
  };

  const handleSubmit = () => {
    if (!company.trim()) { alert('업체명을 입력해주세요.'); return; }
    if (!selectedComplex) { alert('단지를 선택해주세요.'); return; }
    if (!selectedArea) { alert('평형을 선택해주세요.'); return; }
    if (!amount) { alert('대출 신청금액을 입력해주세요.'); return; }

    const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
    const dongHo = formatDongHo(dong, ho);
    const fullAddress = [roadAddr, selectedComplex.name, dongHo].filter(Boolean).join(' ').trim();

    onAnalyze({
      company: company.trim(),
      address: fullAddress,
      loanAmount: Number(amount),
      interestRate: Number(interestRate),
      duration: Number(duration),
      options: {
        complex_id: selectedComplex.id,
        area_id: selectedArea.id,
        complex_name: selectedComplex.name,
        pyeong: derivedPyeong,
        registry_ic_id: registryResult?.ic_id ?? null,
      },
    });
  };

  const submitting = loading;

  return (
    <div className="direct-analysis-form">
      <div className="daf-section">
        <h3>분석 대상 정보</h3>

        <div className="daf-field">
          <label>업체명 <span className="daf-required">*</span></label>
          <input type="text" value={company} onChange={(e) => setCompany(e.target.value)}
                 disabled={submitting} maxLength={200} />
          <div className="daf-hint">분석 결과에 표기될 라벨 (실 신청건이 아니라 임의 입력 가능)</div>
        </div>

        {/* 시도/시군구/읍면동 */}
        <div className="daf-field" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div>
            <label>시도 <span className="daf-required">*</span></label>
            <select value={selectedSido?.code ?? ''}
                    onChange={(e) => setSelectedSido(sidoList.find((s) => s.code === e.target.value) ?? null)}
                    disabled={submitting} className="daf-select">
              <option value="">선택하세요</option>
              {sidoList.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label>시군구 <span className="daf-required">*</span></label>
            <select value={selectedSigungu?.code ?? ''}
                    onChange={(e) => setSelectedSigungu(sigunguList.find((s) => s.code === e.target.value) ?? null)}
                    disabled={submitting || !selectedSido} className="daf-select">
              <option value="">{selectedSido ? '선택하세요' : '시도 먼저'}</option>
              {sigunguList.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </div>
          <div>
            <label>읍면동</label>
            <select value={selectedDong?.code ?? ''}
                    onChange={(e) => setSelectedDong(dongList.find((d) => d.code === e.target.value) ?? null)}
                    disabled={submitting || !selectedSigungu || dongList.length === 0} className="daf-select">
              <option value="">
                {!selectedSigungu ? '시군구 먼저' : dongList.length === 0 ? '매핑 없음 (생략 가능)' : '선택하세요'}
              </option>
              {dongList.map((d) => <option key={d.code} value={d.code}>{d.name}</option>)}
            </select>
          </div>
        </div>

        {/* 단지 검색 */}
        {selectedSigungu && (
          <div className="daf-field">
            <label>단지 <span className="daf-required">*</span></label>
            <input type="text" value={complexQuery}
                   onChange={(e) => setComplexQuery(e.target.value)}
                   placeholder={`${selectedSigungu.name} 내 단지명 검색 (선택사항)`}
                   disabled={submitting} />
            <div className="daf-hint">
              {complexLoading && <span className="daf-status loading">⏳ 단지 검색 중…</span>}
              {!complexLoading && dongFilterFallback && (
                <span className="daf-status warning">⚠ 이 동의 단지 정보가 부족하여 시군구 전체 표시 중</span>
              )}
              {!complexLoading && complexTotal > complexResults.length && (
                <span className="daf-status warning">
                  결과 {complexTotal.toLocaleString()}건 중 상위 {complexResults.length}건 표시
                </span>
              )}
              {!complexLoading && selectedComplex && (
                <span className="daf-status success">
                  ✓ 선택: <strong>{selectedComplex.name}</strong>
                </span>
              )}
            </div>

            {!selectedComplex && complexResults.length > 0 && (
              <div className="daf-complex-list">
                {complexResults.map((c) => (
                  <button key={c.id} type="button" onClick={() => setSelectedComplex(c)}
                          disabled={submitting} className="daf-complex-item">
                    <strong>{c.name}</strong>
                    {c.total_households != null && (
                      <span className="daf-complex-units">{c.total_households.toLocaleString()}세대</span>
                    )}
                  </button>
                ))}
              </div>
            )}

            {selectedComplex && (
              <button type="button" onClick={() => { setSelectedComplex(null); setAreas([]); }}
                      disabled={submitting} className="daf-link-btn">
                ← 다른 단지 선택
              </button>
            )}
          </div>
        )}

        {selectedComplex && (
          <>
            {selectedComplex.road_address && (
              <div className="daf-field">
                <label>도로명 주소</label>
                <input type="text" disabled readOnly
                       value={[selectedComplex.road_address, selectedComplex.name, formatDongHo(dong, ho)].filter(Boolean).join(' ')} />
              </div>
            )}
            {selectedComplex.address && (
              <div className="daf-field">
                <label>지번 주소</label>
                <input type="text" disabled readOnly
                       value={[selectedComplex.address, selectedComplex.name, formatDongHo(dong, ho)].filter(Boolean).join(' ')} />
              </div>
            )}

            {/* 동·호 */}
            <div className="daf-field">
              <label>동 / 호수</label>
              <div className="daf-dong-ho">
                <input type="text" value={dong} onChange={(e) => setDong(e.target.value)}
                       placeholder="예: 3" disabled={submitting} />
                <input type="text" value={ho} onChange={(e) => setHo(e.target.value)}
                       placeholder="예: 502" disabled={submitting} />
              </div>
            </div>

            {/* 등기부등본 */}
            <div className="daf-field">
              <button type="button" onClick={handleFetchRegistry}
                      disabled={submitting || registryLoading || !dong.trim() || !ho.trim()}
                      className="daf-registry-btn"
                      style={{
                        background: registryLoading ? '#7DCCE5' : '#006FBD',
                        cursor: registryLoading ? 'wait' : 'pointer',
                        opacity: (!dong.trim() || !ho.trim()) ? 0.5 : 1,
                      }}>
                {registryLoading ? '발급 요청 중...' : '📄 등기부등본 가져오기'}
              </button>
              {registryLoading && (
                <div className="daf-registry-hint">등기부등본 조회에 시간이 소요될 수 있습니다.</div>
              )}
              {registryResult && (
                <div className={`daf-registry-result ${registryResult.error ? 'err' : 'ok'}`}>
                  {registryResult.error || (
                    <>
                      <strong>발급 {registryResult.status}</strong>
                      {registryResult.ic_id ? ` (ID: ${registryResult.ic_id})` : ''}
                      {registryResult.pdf_url && registryResult.ic_id && (
                        <>
                          {' · '}
                          <button type="button" className="daf-link-btn-inline"
                                  onClick={() => registryApi.openPdf(registryResult.ic_id!)}>
                            PDF 다운로드
                          </button>
                        </>
                      )}
                      {registryResult.cached && ' · 캐시 (재발급 비용 0)'}
                    </>
                  )}
                </div>
              )}
            </div>

            {/* 평형 — 등기부 표제부 전용면적 기반 자동 선택, 다르면 수정 가능 */}
            <div className="daf-field">
              <label>평형 <span className="daf-required">*</span></label>
              {areas.length === 0 ? (
                <div className="daf-hint">
                  <span className="daf-status warning">⚠ 이 단지의 평형 정보가 수집되지 않았습니다.</span>
                </div>
              ) : (
                <>
                  <select value={selectedArea?.id ?? ''}
                          onChange={(e) => setSelectedArea(areas.find((a) => a.id === parseInt(e.target.value, 10)) ?? null)}
                          disabled={submitting} className="daf-select">
                    <option value="">{registryResult?.status === 'completed' ? '직접 선택' : '등기부 발급 후 자동 선택됩니다'}</option>
                    {areas.map((a) => (
                      <option key={a.id} value={a.id}>
                        전용 {a.exclusive_m2.toFixed(0)}㎡
                        {a.pyeong ? ` (${Math.round(a.pyeong)}평)` : ''}
                      </option>
                    ))}
                  </select>
                  {registryExclusiveM2 != null && (
                    <div className="daf-hint">
                      <span className="daf-status success">
                        등기부 전용 {registryExclusiveM2.toFixed(2)}㎡ 기반 자동 선택 — 다르면 selector 에서 변경
                      </span>
                    </div>
                  )}
                  {selectedArea && derivedPyeong && (
                    <div className="daf-hint">≈ 약 <strong>{derivedPyeong}평</strong></div>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* 대출 조건 */}
      <div className="daf-section">
        <h3>대출 조건</h3>
        <div className="daf-field" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 }}>
          <div>
            <label>대출 신청금액 <span className="daf-required">*</span></label>
            <div className="daf-amount">
              <input type="number" value={amount} onChange={(e) => setAmount(e.target.value)}
                     placeholder="800000000" disabled={submitting} />
              <span className="daf-unit">원</span>
            </div>
          </div>
          <div>
            <label>금리</label>
            <div className="daf-amount">
              <input type="number" value={interestRate} onChange={(e) => setInterestRate(e.target.value)}
                     step="0.1" min="0" max="100" disabled={submitting} />
              <span className="daf-unit">%</span>
            </div>
          </div>
          <div>
            <label>대출기간</label>
            <select value={duration} onChange={(e) => setDuration(e.target.value)}
                    disabled={submitting} className="daf-select">
              <option value="6">6개월</option>
              <option value="12">12개월</option>
              <option value="18">18개월</option>
              <option value="24">24개월</option>
              <option value="36">36개월</option>
              <option value="48">48개월</option>
              <option value="60">60개월</option>
            </select>
          </div>
        </div>
      </div>

      <button type="button" onClick={handleSubmit} disabled={submitting} className="daf-submit-btn">
        {submitting ? '분석 중...' : '분석'}
      </button>
    </div>
  );
}
