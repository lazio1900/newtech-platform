import { useEffect, useMemo, useRef, useState } from 'react';
import { User, LoanApplication } from '../types/loan';
import { submitApplication, getApplications } from '../api/applications';
import { complexesApi } from '../api/complexes';
import { regionsApi, RegionItem, DongItem } from '../api/regions';
import { registryApi } from '../api/registry';
import type { Area, Complex } from '@/types/complex';
import Settings from './Settings';
import UserProfileMenu from './UserProfileMenu';
import './CustomerDashboard.css';

interface CustomerDashboardProps {
  user: User;
  onLogout: () => void;
}

const M2_PER_PYEONG = 3.3058;

const STATUS_COLOR: Record<string, string> = {
  '접수완료': '#006FBD',
  '심사중': '#051C48',
  '승인': '#20c997',
  '반려': '#EF5350',
  '보류': '#9CA3AF',
};

export default function CustomerDashboard({ user, onLogout }: CustomerDashboardProps) {
  const [activeTab, setActiveTab] = useState<'apply' | 'history' | 'settings'>('apply');

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

  // 평형 (DB에 등록된 areas 중에서만 선택)
  const [areas, setAreas] = useState<Area[]>([]);
  const [selectedArea, setSelectedArea] = useState<Area | null>(null);

  // 동·호·금액
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

  const handleFetchRegistry = async () => {
    if (!selectedComplex || !dong.trim() || !ho.trim()) return;
    setRegistryLoading(true);
    setRegistryResult(null);
    setRegistryExclusiveM2(null);
    try {
      // backend 가 complex_id 기반으로 4단계 후보 chain (지번/도로명 × 단지명 유무) 으로 매칭 시도.
      // payload.address 는 후보가 못 만들어진 예외 경로의 fallback 용도.
      const roadAddr = selectedComplex.road_address || selectedComplex.address || '';
      const fullAddress = `${roadAddr} ${selectedComplex.name}`.trim();

      const res = await registryApi.request({
        address: fullAddress,
        dong: dong.trim(),
        ho: ho.trim(),
        type: '집합건물',
        complex_id: selectedComplex.id,
      });

      // 즉시 완료된 경우 (캐시 hit 등)
      if (res.status === 'completed' && res.ic_id) {
        setRegistryResult({
          status: res.status, ic_id: res.ic_id,
          pdf_url: registryApi.pdfUrl(res.ic_id),
          cached: res.cached, error: res.error_message,
        });
        applyAreaSuggestion(res.ic_id, selectedComplex.id);
        return;
      }

      // 폴링 (최대 60초, 5초 간격)
      const icId = res.ic_id;
      if (!icId) {
        setRegistryResult({
          status: res.status, error: res.error_message || '발급 ID 미발급',
        });
        return;
      }
      setRegistryResult({ status: 'issuing', ic_id: icId });

      const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
      let elapsed = 0;
      // 등기부 API 의 PDF 다운로드 폴링이 최대 120초. 여유 두고 180초.
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
            setRegistryResult({
              status: 'failed', ic_id: icId, error: cur.error_message || '발급 실패',
            });
            return;
          }
          // 'issuing' / 'requested' 면 계속 폴링
          setRegistryResult({ status: cur.status, ic_id: icId });
        } catch (pollErr) {
          // 일시 오류면 다음 폴링 시도
        }
      }
      setRegistryResult({
        status: 'timeout', ic_id: icId,
        error: '발급이 3분 안에 완료되지 않았습니다. 잠시 후 다시 확인해주세요.',
      });
    } catch (e: any) {
      setRegistryResult({
        error: e?.response?.data?.detail?.message
            || e?.response?.data?.detail
            || e?.message
            || '등기부등본 발급 요청에 실패했습니다',
      });
    } finally {
      setRegistryLoading(false);
    }
  };
  const [amount, setAmount] = useState<string>('');
  const [duration, setDuration] = useState<string>('12');

  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const debounceRef = useRef<number | null>(null);

  // 시도 목록 로드 (1회)
  useEffect(() => {
    regionsApi.listSido().then(setSidoList).catch(() => setSidoList([]));
  }, []);

  // 신청 내역 탭 진입 시 fetch
  useEffect(() => {
    if (activeTab === 'history') fetchApplications();
  }, [activeTab]);

  const fetchApplications = async () => {
    try {
      const data = await getApplications();
      setApplications(data);
    } catch (err) {
      console.error('Failed to fetch applications:', err);
    }
  };

  // 시도 선택 → 시군구 로드
  useEffect(() => {
    if (!selectedSido) {
      setSigunguList([]);
      setSelectedSigungu(null);
      return;
    }
    regionsApi
      .listSigungu(selectedSido.code)
      .then(setSigunguList)
      .catch(() => setSigunguList([]));
    setSelectedSigungu(null);
    setSelectedDong(null);
    setDongList([]);
    resetComplexAndDownstream();
  }, [selectedSido]);

  // 시군구 선택 → 읍면동 로드 + 단지 검색 trigger
  useEffect(() => {
    setSelectedDong(null);
    resetComplexAndDownstream();
    if (!selectedSigungu) {
      setDongList([]);
      return;
    }
    regionsApi
      .listEupmyeondong(selectedSigungu.code)
      .then(setDongList)
      .catch(() => setDongList([]));
    runComplexSearch(complexQuery);
  }, [selectedSigungu]);

  // 동 선택 → 단지 검색 다시 (dong_code 필터)
  useEffect(() => {
    if (!selectedSigungu) return;
    setSelectedComplex(null);
    runComplexSearch(complexQuery);
  }, [selectedDong]);

  // 단지 검색 input 변경 → 디바운스
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

  // 단지 선택 → 평형 로드. 1건이면 자동 선택.
  useEffect(() => {
    if (!selectedComplex) {
      setAreas([]);
      setSelectedArea(null);
      return;
    }
    let cancelled = false;
    complexesApi
      .listAreas(selectedComplex.id)
      .then((data) => {
        if (cancelled) return;
        setAreas(data);
        setSelectedArea(data.length === 1 ? data[0] : null);
      })
      .catch(() => {
        if (!cancelled) {
          setAreas([]);
          setSelectedArea(null);
        }
      });
    return () => {
      cancelled = true;
    };
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
      // 1차: 동 선택됐으면 dong_code 필터로 좁힘
      let res = await complexesApi.list({
        ...baseParams,
        dong_code: selectedDong?.code || undefined,
      });
      // 동 필터 적용했는데 결과 0건 → 시군구 전체로 fallback (단지 dong_code 백필 부족 케이스)
      if (selectedDong && res.total === 0) {
        const fallback = await complexesApi.list(baseParams);
        if (fallback.total > 0) {
          setDongFilterFallback(true);
          res = fallback;
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

  // 단지 주소 — DB의 도로명/지번 주소 우선, 없으면 시도/시군구/동/단지명 조합
  const baseComplexAddress = (): string => {
    if (!selectedComplex) return '';
    if (selectedComplex.road_address) return selectedComplex.road_address;
    if (selectedComplex.address) return selectedComplex.address;
    return [
      selectedSido?.name,
      selectedSigungu?.name,
      selectedDong?.name,
      selectedComplex.name,
    ].filter(Boolean).join(' ');
  };

  // 사용자는 숫자만 입력 ('102'). 표시·저장 시 '동'/'호' 접미사 부여.
  const formatDongHo = (d: string | null | undefined, h: string | null | undefined): string => {
    const parts: string[] = [];
    if (d && String(d).trim()) parts.push(`${String(d).trim()}동`);
    if (h && String(h).trim()) parts.push(`${String(h).trim()}호`);
    return parts.join(' ');
  };

  // property_address 는 단지 주소 + 동/호 합쳐서 저장 (화면 표시 시 한 줄로 보이도록)
  const buildFullAddress = (): string => {
    const dongHo = formatDongHo(dong, ho);
    return [baseComplexAddress(), dongHo].filter(Boolean).join(' ');
  };

  const handleSubmit = async () => {
    if (!selectedSido || !selectedSigungu) {
      alert('시도/시군구를 선택해주세요.');
      return;
    }
    if (!selectedComplex) {
      alert('단지를 선택해주세요.');
      return;
    }
    if (!selectedArea) {
      alert('평형을 선택해주세요. (등록된 평형 정보가 없으면 다른 단지를 선택해주세요)');
      return;
    }
    if (!amount || !duration) {
      alert('신청금액과 대출기간을 입력해주세요.');
      return;
    }
    const loanAmount = parseInt(amount, 10);
    if (!Number.isFinite(loanAmount) || loanAmount <= 0) {
      alert('신청금액을 올바르게 입력해주세요.');
      return;
    }

    setSubmitting(true);
    try {
      const data = await submitApplication({
        company_name: user.company_name ?? '',
        ceo_name: user.ceo_name ?? '',
        property_address: buildFullAddress(),
        loan_amount: loanAmount,
        loan_duration: parseInt(duration, 10),
        complex_id: selectedComplex.id,
        complex_name: selectedComplex.name,
        area_id: selectedArea.id,
        exclusive_m2: selectedArea.exclusive_m2,
        pyeong: derivedPyeong,
        dong: dong.trim() || null,
        ho: ho.trim() || null,
        registry_ic_id: registryResult?.ic_id ?? null,
      });
      if (data.status === 'success') {
        alert('대출 신청이 완료되었습니다.');
        // 폼 초기화
        setSelectedSido(null); setSelectedSigungu(null); setSelectedDong(null);
        setSigunguList([]); setDongList([]);
        resetComplexAndDownstream();
        setAmount(''); setDuration('12');
        setRegistryResult(null);
        setActiveTab('history');
      }
    } catch {
      alert('서버에 연결할 수 없습니다.');
    } finally {
      setSubmitting(false);
    }
  };

  const formatAmount = (value: number): string => {
    if (!value) return '-';
    return `${(value / 100000000).toFixed(1)}억원`;
  };

  return (
    <div className="customer-dashboard">
      <header className="dashboard-header">
        <div className="header-left">
          <img src="/capital_CI.png" alt="JB우리캐피탈" className="header-logo clickable"
               onClick={() => setActiveTab('history')} />
          <span className="header-divider">|</span>
          <h1>대출 신청</h1>
        </div>
        <div className="header-right">
          {/* 사용자 정보 / 로그아웃은 좌측 사이드바 하단 사용자 메뉴로 이동 */}
        </div>
      </header>

      <div className="dashboard-body">
        <nav className="sidebar">
          <button className={`sidebar-btn ${activeTab === 'apply' ? 'active' : ''}`}
                  onClick={() => setActiveTab('apply')}>대출 신청</button>
          <button className={`sidebar-btn ${activeTab === 'history' ? 'active' : ''}`}
                  onClick={() => setActiveTab('history')}>신청 내역</button>

          {/* 하단 — 사용자 프로필 + 드롭다운. customer 는 admin 패널 미노출 */}
          <div className="sidebar-bottom">
            <UserProfileMenu
              user={user}
              onOpenAccount={() => setActiveTab('settings')}
              onOpenAdminPanel={() => { /* customer 는 admin 아니라 호출 안 됨 */ }}
              onLogout={onLogout}
            />
          </div>
        </nav>

        <div className="dashboard-content">
        {activeTab === 'apply' && (
          <div className="apply-card">
            <h2>대출 신청 정보 입력</h2>
            <div className="apply-subtitle">
              시도 → 시군구 → 단지를 선택한 후 평형/동·호와 대출 조건을 입력하세요.
            </div>

            <div className="apply-info-box">
              <h3>신청 업체 정보</h3>
              <div className="info-grid">
                <div className="info-item"><span className="info-label">대부업체명</span><span className="info-value">{user.company_name}</span></div>
                <div className="info-item"><span className="info-label">대표이사</span><span className="info-value">{user.ceo_name}</span></div>
                <div className="info-item"><span className="info-label">사업자등록번호</span><span className="info-value">{user.business_number}</span></div>
                <div className="info-item"><span className="info-label">연락처</span><span className="info-value">{user.phone}</span></div>
              </div>
            </div>

            <div className="apply-form-box">
              <h3>담보 물건 정보</h3>

              {/* 시도 / 시군구 / 읍면동 */}
              <div className="apply-field" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
                <div>
                  <label>시도 <span style={{ color: '#EF5350' }}>*</span></label>
                  <select
                    value={selectedSido?.code ?? ''}
                    onChange={(e) => {
                      const code = e.target.value;
                      setSelectedSido(sidoList.find((s) => s.code === code) ?? null);
                    }}
                    disabled={submitting}
                    className="duration-select"
                    style={{ width: '100%' }}
                  >
                    <option value="">선택하세요</option>
                    {sidoList.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label>시군구 <span style={{ color: '#EF5350' }}>*</span></label>
                  <select
                    value={selectedSigungu?.code ?? ''}
                    onChange={(e) => {
                      const code = e.target.value;
                      setSelectedSigungu(sigunguList.find((s) => s.code === code) ?? null);
                    }}
                    disabled={submitting || !selectedSido}
                    className="duration-select"
                    style={{ width: '100%' }}
                  >
                    <option value="">{selectedSido ? '선택하세요' : '시도 먼저'}</option>
                    {sigunguList.map((s) => (
                      <option key={s.code} value={s.code}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label>읍면동</label>
                  <select
                    value={selectedDong?.code ?? ''}
                    onChange={(e) => {
                      const code = e.target.value;
                      setSelectedDong(dongList.find((d) => d.code === code) ?? null);
                    }}
                    disabled={submitting || !selectedSigungu || dongList.length === 0}
                    className="duration-select"
                    style={{ width: '100%' }}
                  >
                    <option value="">
                      {!selectedSigungu
                        ? '시군구 먼저'
                        : dongList.length === 0
                          ? '매핑 없음 (생략 가능)'
                          : '선택하세요'}
                    </option>
                    {dongList.map((d) => (
                      <option key={d.code} value={d.code}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {selectedSigungu && dongList.length === 0 && (
                <div className="field-hint" style={{ marginTop: -8, marginBottom: 12 }}>
                  <span className="match-status warning">
                    ⚠ 이 시군구의 읍면동 매핑이 아직 추가되지 않았습니다 (생략 후 진행 가능)
                  </span>
                </div>
              )}

              {/* 단지 검색 */}
              {selectedSigungu && (
                <div className="apply-field">
                  <label>단지 <span style={{ color: '#EF5350' }}>*</span></label>
                  <input
                    type="text"
                    value={complexQuery}
                    onChange={(e) => setComplexQuery(e.target.value)}
                    placeholder={`${selectedSigungu.name} 내 단지명 검색 (선택사항)`}
                    disabled={submitting}
                  />
                  <div className="field-hint">
                    {complexLoading && <span className="match-status loading">⏳ 단지 검색 중…</span>}
                    {!complexLoading && dongFilterFallback && (
                      <span className="match-status warning">
                        ⚠ 이 동의 단지 정보가 아직 부족하여 시군구 전체 단지 표시 중
                      </span>
                    )}
                    {!complexLoading && complexTotal > complexResults.length && (
                      <span className="match-status warning">
                        결과 {complexTotal.toLocaleString()}건 중 상위 {complexResults.length}건 표시 (검색어로 좁혀주세요)
                      </span>
                    )}
                    {!complexLoading && selectedComplex && (
                      <span className="match-status success">
                        ✓ 선택: <strong style={{ marginLeft: 4 }}>{selectedComplex.name}</strong>
                      </span>
                    )}
                  </div>

                  {!selectedComplex && complexResults.length > 0 && (
                    <div style={{
                      marginTop: 8,
                      maxHeight: 240,
                      overflowY: 'auto',
                      border: '1px solid #E0EAF4',
                      borderRadius: 6,
                      background: '#FAFCFE',
                    }}>
                      {complexResults.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => setSelectedComplex(c)}
                          disabled={submitting}
                          style={{
                            display: 'block',
                            width: '100%',
                            padding: '10px 14px',
                            background: 'transparent',
                            border: 'none',
                            borderBottom: '1px solid #EEF2F7',
                            textAlign: 'left',
                            cursor: 'pointer',
                            fontFamily: 'Noto Sans KR, sans-serif',
                            fontSize: 13,
                            color: '#1F2A3C',
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = '#EEF4FB')}
                          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                        >
                          <strong>{c.name}</strong>
                          {c.total_households != null && (
                            <span style={{ marginLeft: 8, fontSize: 12, color: '#6B7785' }}>
                              {c.total_households.toLocaleString()}세대
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {selectedComplex && (
                    <button
                      type="button"
                      onClick={() => { setSelectedComplex(null); setAreas([]); }}
                      disabled={submitting}
                      style={{
                        marginTop: 6, background: 'transparent', color: '#006FBD',
                        border: 'none', padding: 0, cursor: 'pointer',
                        fontSize: 12, textDecoration: 'underline',
                      }}
                    >
                      ← 다른 단지 선택
                    </button>
                  )}
                </div>
              )}

              {/* 단지 선택 후 표시 영역 */}
              {selectedComplex && (
                <>
                  {/* 도로명 주소 (readonly) — 동/호 입력하면 자동으로 합쳐져 표시 */}
                  {selectedComplex.road_address && (
                    <div className="apply-field">
                      <label>도로명 주소</label>
                      <input
                        type="text"
                        value={[selectedComplex.road_address, selectedComplex.name, formatDongHo(dong, ho)].filter(Boolean).join(' ')}
                        disabled readOnly
                      />
                    </div>
                  )}

                  {/* 지번 주소 (readonly) */}
                  {selectedComplex.address && (
                    <div className="apply-field">
                      <label>지번 주소</label>
                      <input
                        type="text"
                        value={[selectedComplex.address, selectedComplex.name, formatDongHo(dong, ho)].filter(Boolean).join(' ')}
                        disabled readOnly
                      />
                    </div>
                  )}

                  {/* 도로명·지번 모두 없는 예외 케이스: 조합 주소 fallback */}
                  {!selectedComplex.road_address && !selectedComplex.address && (
                    <div className="apply-field">
                      <label>주소</label>
                      <input type="text" value={buildFullAddress()} disabled readOnly />
                    </div>
                  )}

                  {/* 동·호 */}
                  <div className="apply-field">
                    <label>동 / 호수</label>
                    <div className="dong-ho-row">
                      <input type="text" value={dong}
                             onChange={(e) => setDong(e.target.value)}
                             placeholder="예: 3" disabled={submitting} />
                      <input type="text" value={ho}
                             onChange={(e) => setHo(e.target.value)}
                             placeholder="예: 502" disabled={submitting} />
                    </div>
                  </div>


                  {/* 등기부등본 가져오기 */}
                  <div className="apply-field" style={{ marginTop: 12 }}>
                    <button
                      type="button"
                      onClick={handleFetchRegistry}
                      disabled={
                        submitting || registryLoading ||
                        !dong.trim() || !ho.trim()
                      }
                      style={{
                        width: '100%', padding: '10px 16px',
                        background: registryLoading ? '#7DCCE5' : '#006FBD',
                        color: '#fff', border: 'none', borderRadius: 6,
                        fontSize: 14, fontWeight: 600,
                        cursor: registryLoading ? 'wait' : 'pointer',
                        opacity: (!dong.trim() || !ho.trim()) ? 0.5 : 1,
                      }}
                    >
                      {registryLoading ? '발급 요청 중...' : '📄 등기부등본 가져오기'}
                    </button>
                    {registryLoading && (
                      <div style={{
                        marginTop: 6, fontSize: 12, color: '#6B7785', textAlign: 'center',
                      }}>
                        등기부등본 조회에 시간이 소요될 수 있습니다.
                      </div>
                    )}
                    {registryResult && (
                      <div style={{
                        marginTop: 8, padding: 10, borderRadius: 4,
                        background: registryResult.error ? '#FEE2E2' : '#D1FAE5',
                        fontSize: 12, color: registryResult.error ? '#991B1B' : '#065F46',
                      }}>
                        {registryResult.error || (
                          <>
                            <strong>발급 {registryResult.status}</strong>
                            {registryResult.ic_id ? ` (ID: ${registryResult.ic_id})` : ''}
                            {registryResult.pdf_url && registryResult.ic_id && (
                              <>
                                {' · '}
                                <button type="button"
                                  onClick={() => registryApi.openPdf(registryResult.ic_id!)}
                                  style={{
                                    background: 'transparent', border: 'none', padding: 0,
                                    color: '#006FBD', textDecoration: 'underline', cursor: 'pointer',
                                    fontSize: 12, fontWeight: 600,
                                  }}>
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
                  <div className="apply-field">
                    <label>평형 <span style={{ color: '#EF5350' }}>*</span></label>
                    {areas.length === 0 ? (
                      <div className="field-hint">
                        <span className="match-status warning">
                          ⚠ 이 단지의 평형 정보가 아직 수집되지 않았습니다. 다른 단지를 선택해주세요.
                        </span>
                      </div>
                    ) : (
                      <>
                        <select
                          value={selectedArea?.id ?? ''}
                          onChange={(e) => {
                            const id = parseInt(e.target.value, 10);
                            setSelectedArea(areas.find((a) => a.id === id) ?? null);
                          }}
                          disabled={submitting}
                          className="duration-select"
                        >
                          <option value="">
                            {registryResult?.status === 'completed' ? '직접 선택' : '등기부 발급 후 자동 선택됩니다'}
                          </option>
                          {areas.map((a) => (
                            <option key={a.id} value={a.id}>
                              전용 {a.exclusive_m2.toFixed(2)}㎡
                              {a.pyeong ? ` (${Math.round(a.pyeong)}평)` : ''}
                              {a.supply_m2 ? ` · 공급 ${a.supply_m2.toFixed(2)}㎡` : ''}
                            </option>
                          ))}
                        </select>
                        {registryExclusiveM2 != null && (
                          <div className="field-hint">
                            <span className="match-status success">
                              등기부 전용 {registryExclusiveM2.toFixed(2)}㎡ 기반 자동 선택 — 다르면 selector 에서 변경
                            </span>
                          </div>
                        )}
                        {selectedArea && derivedPyeong && (
                          <div className="field-hint">
                            ≈ 약 <strong>{derivedPyeong}평</strong>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </>
              )}
            </div>

            <div className="apply-form-box">
              <h3>대출 조건</h3>

              <div className="apply-field">
                <label>대출 신청금액 <span style={{ color: '#EF5350' }}>*</span></label>
                <div className="apply-amount-row">
                  <input type="number" value={amount}
                         onChange={(e) => setAmount(e.target.value)}
                         placeholder="예: 800000000" disabled={submitting} />
                  <span className="unit">원</span>
                </div>
                {amount && Number.isFinite(parseInt(amount, 10)) && parseInt(amount, 10) > 0 && (
                  <div className="field-hint">≈ <strong>{formatAmount(parseInt(amount, 10))}</strong></div>
                )}
              </div>
              <div className="apply-field">
                <label>적용금리</label>
                <div className="apply-amount-row">
                  <input type="text" value="7.5" disabled readOnly className="rate-input-readonly" />
                  <span className="unit">%</span>
                </div>
              </div>
              <div className="apply-field">
                <label>신청 대출기간 <span style={{ color: '#EF5350' }}>*</span></label>
                <div className="apply-amount-row">
                  <select value={duration}
                          onChange={(e) => setDuration(e.target.value)}
                          disabled={submitting} className="duration-select">
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

            <button className="submit-btn" onClick={handleSubmit} disabled={submitting}>
              {submitting ? '신청 중...' : '대출 신청'}
            </button>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="history-card">
            <h2>신청 내역</h2>
            {applications.length === 0 ? (
              <p className="empty-text">신청 내역이 없습니다.</p>
            ) : (
              <table className="history-table">
                <thead>
                  <tr>
                    <th>신청번호</th>
                    <th>단지 / 전용 / 동·호</th>
                    <th>주소</th>
                    <th>신청금액</th>
                    <th>금리</th>
                    <th>대출기간</th>
                    <th>신청일시</th>
                    <th>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {applications.map((app) => (
                    <tr key={app.id}>
                      <td>{app.id}</td>
                      <td>
                        {app.complex_name && <div><strong>{app.complex_name}</strong></div>}
                        {app.exclusive_m2 != null && (
                          <div className="cell-secondary">
                            {app.exclusive_m2.toFixed(0)}㎡{app.pyeong ? ` (${app.pyeong}평)` : ''}
                          </div>
                        )}
                        {(app.dong || app.ho) && (
                          <div className="cell-secondary">
                            {formatDongHo(app.dong, app.ho)}
                          </div>
                        )}
                      </td>
                      <td>{app.property_address}</td>
                      <td>{formatAmount(app.loan_amount)}</td>
                      <td>7.5%</td>
                      <td>{app.loan_duration}개월</td>
                      <td>{app.created_at}</td>
                      <td>
                        <span className="status-badge"
                              style={{ backgroundColor: STATUS_COLOR[app.status] || '#999' }}>
                          {app.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {activeTab === 'settings' && (
          <Settings user={user} />
        )}
        </div>
      </div>
    </div>
  );
}
