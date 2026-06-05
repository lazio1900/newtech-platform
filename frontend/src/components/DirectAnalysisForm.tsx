/**
 * Auditor 직접조회 폼 — customer 의 apply 폼과 동일 흐름(시도/시군구/단지/평형/동·호/등기부) +
 * 분석 조건 입력 → onAnalyze 콜백으로 결과 반환.
 *
 * NOTE: customer 의 apply 폼과 의도적으로 코드를 중복 유지. 양쪽 흐름이 안정화되면 추후
 * 공용 컴포넌트로 추출.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { complexesApi } from '../api/complexes';
import { lendersApi, type Lender } from '../api/lenders';
import { regionsApi, RegionItem, DongItem } from '../api/regions';
import { registryApi } from '../api/registry';
import type { Area, Complex } from '@/types/complex';
import './DirectAnalysisForm.css';

const M2_PER_PYEONG = 3.3058;

export interface DirectAnalyzePayload {
  company: string;
  ceoName: string;
  businessNumber: string;
  creditScoreNice: number | null;
  creditScoreKcb: number | null;
  address: string;
  dong: string;
  ho: string;
  loanAmount: number;
  interestRate: number;
  duration: number;
  options: {
    complex_id?: number | null;
    area_id?: number | null;
    complex_name?: string | null;
    pyeong?: number | null;
    registry_ic_id?: number | null;
    rles_unq_no?: string | null;
  };
}

export interface DirectAnalyzeInitial {
  lenderBusinessNumber?: string | null;
  lenderCompanyName?: string | null;
  complexId?: number | null;
  areaId?: number | null;
  dong?: string | null;
  ho?: string | null;
  registryIcId?: number | null;
  rlesUnqNo?: string | null;
  loanAmount?: number | null;
  interestRate?: number | null;
  loanDuration?: number | null;
}

interface DirectAnalysisFormProps {
  onAnalyze: (payload: DirectAnalyzePayload) => void;
  loading: boolean;
  initial?: DirectAnalyzeInitial | null;
  submitLabel?: string;
  submitLabelBusy?: string;
}

export default function DirectAnalysisForm({
  onAnalyze, loading, initial, submitLabel = '신청', submitLabelBusy = '신청 중...',
}: DirectAnalysisFormProps) {
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

  // 부동산고유번호 (폐쇄망 등기부 조인키, 수기 입력)
  const [rlesUnqNo, setRlesUnqNo] = useState<string>('');

  // 등기부등본 발급
  const [registryLoading, setRegistryLoading] = useState<boolean>(false);
  const [registryResult, setRegistryResult] = useState<{
    status?: string; ic_id?: number | null; pdf_url?: string | null;
    cached?: boolean; error?: string | null;
  } | null>(null);
  // 실제 매칭에 성공한 주소 (잘못된 등기부 가져왔는지 확인용)
  const [registryMatch, setRegistryMatch] = useState<{
    address?: string | null; dong?: string | null; ho?: string | null;
  } | null>(null);
  // 등기부 표제부에서 추출된 전용면적 (자동 평형 제안용)
  const [registryExclusiveM2, setRegistryExclusiveM2] = useState<number | null>(null);

  // 차주(대부업체) — 마스터에서 선택
  const [lenders, setLenders] = useState<Lender[]>([]);
  const [lendersLoading, setLendersLoading] = useState<boolean>(false);
  const [lenderQuery, setLenderQuery] = useState<string>('');
  const [selectedLender, setSelectedLender] = useState<Lender | null>(null);

  // 대출 조건
  const [amount, setAmount] = useState<string>('');
  const [interestRate, setInterestRate] = useState<string>('7.5');
  const [duration, setDuration] = useState<string>('12');

  const debounceRef = useRef<number | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const prefilledRef = useRef<boolean>(false);
  // prefill 중에는 시도/시군구/읍면동 변경 effect 가 하위 선택값을 reset 하지 않도록 가드
  const isPrefillingRef = useRef<boolean>(false);

  // 시도 목록 로드
  useEffect(() => {
    regionsApi.listSido().then(setSidoList).catch(() => setSidoList([]));
  }, []);

  // 대부업체 목록 로드 (한 번)
  useEffect(() => {
    setLendersLoading(true);
    lendersApi.list()
      .then(setLenders)
      .catch(() => setLenders([]))
      .finally(() => setLendersLoading(false));
  }, []);

  // 수정 모드 prefill — initial 들어오면 한 번만 채움
  useEffect(() => {
    if (!initial || prefilledRef.current) return;
    if (initial.dong) setDong(initial.dong);
    if (initial.ho) setHo(initial.ho);
    if (initial.rlesUnqNo) setRlesUnqNo(initial.rlesUnqNo);
    if (initial.loanAmount != null) setAmount(String(initial.loanAmount));
    if (initial.interestRate != null) setInterestRate(String(initial.interestRate));
    if (initial.loanDuration != null) setDuration(String(initial.loanDuration));
    if (initial.registryIcId) {
      setRegistryResult({
        status: 'completed', ic_id: initial.registryIcId,
        pdf_url: registryApi.pdfUrl(initial.registryIcId),
        cached: true, error: null,
      });
    }
    if (initial.complexId) {
      isPrefillingRef.current = true;
      complexesApi.get(initial.complexId)
        .then((co) => setSelectedComplex(co))
        .catch(() => { isPrefillingRef.current = false; });
    }
    prefilledRef.current = true;
  }, [initial]);

  // 단지 prefill 완료 후 시도 자동 선택 (region_code 앞 2자리)
  useEffect(() => {
    if (!isPrefillingRef.current || !selectedComplex || sidoList.length === 0 || selectedSido) return;
    const sigCode = (selectedComplex.region_code ?? '').trim();
    if (sigCode.length < 2) { isPrefillingRef.current = false; return; }
    const sidoItem = sidoList.find((s) => s.code === sigCode.slice(0, 2));
    if (sidoItem) setSelectedSido(sidoItem);
    else isPrefillingRef.current = false;
  }, [selectedComplex, sidoList, selectedSido]);

  // 시군구 로드 후 자동 선택
  useEffect(() => {
    if (!isPrefillingRef.current || !selectedComplex || sigunguList.length === 0 || selectedSigungu) return;
    const sigCode = (selectedComplex.region_code ?? '').trim();
    if (!sigCode) return;
    const sigItem = sigunguList.find((s) => s.code === sigCode);
    if (sigItem) setSelectedSigungu(sigItem);
  }, [selectedComplex, sigunguList, selectedSigungu]);

  // 읍면동 로드 후 자동 선택. ref 해제는 dong 변경 effect 에서 — 그래야 그 effect 가
  // setSelectedComplex(null) 호출을 한 번 skip 한다.
  useEffect(() => {
    if (!isPrefillingRef.current || !selectedComplex || dongList.length === 0 || selectedDong) return;
    const dCode = (selectedComplex.dong_code ?? '').trim();
    if (dCode) {
      const dItem = dongList.find((d) => d.code === dCode);
      if (dItem) { setSelectedDong(dItem); return; }
    }
    // dong_code 매칭 없으면 여기서 prefill 종료 (dong 변경 effect 가 트리거되지 않으므로)
    isPrefillingRef.current = false;
  }, [selectedComplex, dongList, selectedDong]);

  // lenders 로드 후 initial 의 식별 정보로 selectedLender 자동 매칭
  useEffect(() => {
    if (!initial || lenders.length === 0 || selectedLender) return;
    const biz = (initial.lenderBusinessNumber ?? '').trim();
    const name = (initial.lenderCompanyName ?? '').trim();
    const match = lenders.find((l) =>
      (biz && l.business_number === biz) ||
      (!biz && name && l.company_name === name)
    );
    if (match) setSelectedLender(match);
  }, [initial, lenders, selectedLender]);

  // initial.areaId 가 있으면 areas 로드 후 자동 선택 (단일평형 자동 선택보다 우선)
  useEffect(() => {
    if (!initial?.areaId || areas.length === 0) return;
    const match = areas.find((a) => a.id === initial.areaId);
    if (match) setSelectedArea(match);
  }, [initial, areas]);

  const filteredLenders = useMemo(() => {
    const q = lenderQuery.trim().toLowerCase();
    if (!q) return lenders;
    return lenders.filter((l) =>
      l.company_name.toLowerCase().includes(q) ||
      (l.business_number ?? '').toLowerCase().includes(q)
    );
  }, [lenders, lenderQuery]);

  // 시도 → 시군구
  useEffect(() => {
    if (!selectedSido) {
      setSigunguList([]);
      setSelectedSigungu(null);
      return;
    }
    regionsApi.listSigungu(selectedSido.code).then(setSigunguList).catch(() => setSigunguList([]));
    if (!isPrefillingRef.current) {
      setSelectedSigungu(null);
      setSelectedDong(null);
      setDongList([]);
      resetComplexAndDownstream();
    }
  }, [selectedSido]);

  // 시군구 → 읍면동 + 단지 검색
  useEffect(() => {
    if (!isPrefillingRef.current) {
      setSelectedDong(null);
      resetComplexAndDownstream();
    }
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
    if (isPrefillingRef.current) {
      // prefill 시퀀스의 마지막 단계 — 단지를 reset 하지 않고 ref 만 해제
      isPrefillingRef.current = false;
    } else {
      setSelectedComplex(null);
    }
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

  // 표시용(소숫점 2자리) / payload용(정수) 분리 — backend pyeong 컬럼은 Integer
  const derivedPyeongFloat = useMemo<number | null>(() => {
    if (!selectedArea?.exclusive_m2) return null;
    return selectedArea.pyeong ?? selectedArea.exclusive_m2 / M2_PER_PYEONG;
  }, [selectedArea]);
  const derivedPyeong = derivedPyeongFloat != null ? Math.round(derivedPyeongFloat) : null;

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
    setRegistryMatch(null);
    setRegistryExclusiveM2(null);
    try {
      const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
      const fullAddress = `${roadAddr} ${selectedComplex.name}`.trim();
      const res = await registryApi.request({
        address: fullAddress, dong: dong.trim(), ho: ho.trim(),
        type: '집합건물', complex_id: selectedComplex.id,
      });
      if (res.matched_address) {
        setRegistryMatch({
          address: res.matched_address,
          dong: res.matched_dong ?? null,
          ho: res.matched_ho ?? null,
        });
      }
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

  const handleUploadRegistry = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';  // 같은 파일 재선택 가능하게 reset
    if (!file) return;
    if (!selectedComplex) { alert('단지를 먼저 선택해주세요.'); return; }

    setRegistryLoading(true);
    setRegistryResult(null);
    setRegistryMatch(null);
    setRegistryExclusiveM2(null);
    try {
      const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
      const fullAddress = `${roadAddr} ${selectedComplex.name}`.trim();
      const res = await registryApi.upload({
        file,
        address: fullAddress,
        dong: dong.trim() || null,
        ho: ho.trim() || null,
        type: '집합건물',
      });
      setRegistryResult({
        status: res.status, ic_id: res.ic_id,
        pdf_url: res.ic_id ? registryApi.pdfUrl(res.ic_id) : null,
        cached: false, error: res.error_message,
      });
      setRegistryMatch({
        address: `[직접 업로드] ${fullAddress}`,
        dong: dong.trim() || null,
        ho: ho.trim() || null,
      });
      if (res.ic_id) {
        applyAreaSuggestion(res.ic_id, selectedComplex.id);
      }
    } catch (err) {
      const ex = err as { response?: { data?: { detail?: string | { message?: string } } }; message?: string };
      const detail = ex?.response?.data?.detail;
      setRegistryResult({
        error: (typeof detail === 'object' ? detail?.message : detail)
            || ex?.message
            || 'PDF 업로드 실패',
      });
    } finally {
      setRegistryLoading(false);
    }
  };

  const handleSubmit = () => {
    if (!selectedLender) { alert("'대부업체 등록' 탭에서 차주 업체를 먼저 등록·선택해주세요."); return; }
    if (!selectedComplex) { alert('단지를 선택해주세요.'); return; }
    if (!selectedArea) { alert('평형을 선택해주세요.'); return; }
    if (!amount) { alert('대출 신청금액을 입력해주세요.'); return; }

    const rlesUnqNoDigits = rlesUnqNo.replace(/\D/g, '');
    if (rlesUnqNoDigits && rlesUnqNoDigits.length !== 14) {
      alert('부동산고유번호는 숫자 14자리입니다. (예: 1149-1996-233513)'); return;
    }

    const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
    const dongHo = formatDongHo(dong, ho);
    const fullAddress = [roadAddr, selectedComplex.name, dongHo].filter(Boolean).join(' ').trim();

    onAnalyze({
      company: selectedLender.company_name,
      ceoName: selectedLender.ceo_name ?? '',
      businessNumber: selectedLender.business_number ?? '',
      creditScoreNice: selectedLender.credit_score_nice ?? null,
      creditScoreKcb: selectedLender.credit_score_kcb ?? null,
      address: fullAddress,
      dong: dong.trim(),
      ho: ho.trim(),
      loanAmount: Number(amount),
      interestRate: Number(interestRate),
      duration: Number(duration),
      options: {
        complex_id: selectedComplex.id,
        area_id: selectedArea.id,
        complex_name: selectedComplex.name,
        pyeong: derivedPyeong,
        registry_ic_id: registryResult?.ic_id ?? null,
        rles_unq_no: rlesUnqNoDigits || null,
      },
    });
  };

  const submitting = loading;

  return (
    <div className="direct-analysis-form">
      <div className="daf-section">
        <h3>차주(대부업체) 선택</h3>

        <div className="daf-field">
          <label>대부업체 <span className="daf-required">*</span></label>
          {lendersLoading ? (
            <div className="daf-hint"><span className="daf-status loading">⏳ 목록 불러오는 중…</span></div>
          ) : lenders.length === 0 ? (
            <div className="daf-hint">
              <span className="daf-status warning">
                ⚠ 등록된 대부업체가 없습니다. 좌측 '대부업체 등록' 탭에서 먼저 등록하세요.
              </span>
            </div>
          ) : (
            <>
              <select
                value={selectedLender?.id ?? ''}
                onChange={(e) => {
                  const id = parseInt(e.target.value, 10);
                  setSelectedLender(lenders.find((l) => l.id === id) ?? null);
                }}
                disabled={submitting}
                className="daf-select"
              >
                <option value="">선택하세요</option>
                {filteredLenders.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.company_name}{l.business_number ? ` (${l.business_number})` : ''}
                  </option>
                ))}
              </select>
              <input
                type="text"
                value={lenderQuery}
                onChange={(e) => setLenderQuery(e.target.value)}
                placeholder="명칭/사업자번호로 좁히기 (선택)"
                disabled={submitting}
                style={{ marginTop: 6 }}
              />
            </>
          )}
        </div>

        {selectedLender && (
          <div
            className="daf-field"
            style={{
              background: '#F3F8FD', border: '1px solid #DCE7F0', borderRadius: 8,
              padding: 12, display: 'grid',
              gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 8, fontSize: 13,
            }}
          >
            <div><div style={{ color: '#6b7280' }}>대부업체</div><strong>{selectedLender.company_name}</strong></div>
            <div><div style={{ color: '#6b7280' }}>사업자번호</div><strong>{selectedLender.business_number ?? '-'}</strong></div>
            <div><div style={{ color: '#6b7280' }}>대표자명</div><strong>{selectedLender.ceo_name ?? '-'}</strong></div>
            <div>
              <div style={{ color: '#6b7280' }}>신용점수 (NICE / KCB)</div>
              <strong>
                {selectedLender.credit_score_nice ?? '-'} / {selectedLender.credit_score_kcb ?? '-'}
              </strong>
            </div>
          </div>
        )}
      </div>

      <div className="daf-section">
        <h3>담보 물건 정보</h3>

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
                    {c.address && (
                      <span className="daf-complex-addr">{c.address}</span>
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

            {/* 부동산고유번호 (폐쇄망 등기부 조인키) */}
            <div className="daf-field">
              <label>부동산고유번호</label>
              <input type="text" value={rlesUnqNo}
                     onChange={(e) => setRlesUnqNo(e.target.value)}
                     placeholder="예: 1149-1996-233513 (숫자 14자리)" disabled={submitting} />
            </div>

            {/* 등기부등본 */}
            <div className="daf-field">
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                <button type="button" onClick={handleFetchRegistry}
                        disabled={submitting || registryLoading || !dong.trim() || !ho.trim()}
                        className="daf-registry-btn"
                        style={{
                          background: registryLoading ? '#7DCCE5' : '#006FBD',
                          cursor: registryLoading ? 'wait' : 'pointer',
                          opacity: (!dong.trim() || !ho.trim()) ? 0.5 : 1,
                        }}>
                  {registryLoading ? '처리 중...' : '📄 등기부등본 가져오기'}
                </button>
                <span style={{ color: '#9CA3AF', fontSize: 12 }}>또는</span>
                <button type="button" onClick={() => uploadInputRef.current?.click()}
                        disabled={submitting || registryLoading}
                        style={{
                          padding: '8px 14px', background: '#fff', color: '#006FBD',
                          border: '1px solid #006FBD', borderRadius: 6, fontWeight: 600,
                          cursor: registryLoading ? 'wait' : 'pointer',
                        }}>
                  ⬆ PDF 직접 업로드
                </button>
                <input ref={uploadInputRef} type="file" accept="application/pdf,.pdf"
                       style={{ display: 'none' }} onChange={handleUploadRegistry} />
              </div>
              {registryLoading && (
                <div className="daf-registry-hint">처리에 시간이 소요될 수 있습니다.</div>
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
                  {registryMatch?.address && (
                    <div style={{ marginTop: 6, fontSize: 12, color: '#374151' }}>
                      ↳ <strong>매칭 주소</strong>: {registryMatch.address}
                      {registryMatch.dong ? ` ${registryMatch.dong}동` : ''}
                      {registryMatch.ho ? ` ${registryMatch.ho}호` : ''}
                      <span style={{ color: '#9CA3AF', marginLeft: 6 }}>
                        — 이 주소가 의도한 물건과 다르면 다시 조회하거나 PDF 직접 업로드를 사용하세요.
                      </span>
                    </div>
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
                        전용 {a.exclusive_m2.toFixed(2)}㎡
                        {a.pyeong ? ` (${a.pyeong.toFixed(2)}평)` : ''}
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
                  {selectedArea && derivedPyeongFloat != null && (
                    <div className="daf-hint">≈ 약 <strong>{derivedPyeongFloat.toFixed(2)}평</strong></div>
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
        {submitting ? submitLabelBusy : submitLabel}
      </button>
    </div>
  );
}
