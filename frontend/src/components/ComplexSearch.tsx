import { useEffect, useRef, useState } from 'react';
import { complexesApi } from '@/api/complexes';
import type { Area, Complex } from '@/types/complex';

interface ComplexSearchProps {
  selectedComplex: Complex | null;
  selectedArea: Area | null;
  onSelectComplex: (complex: Complex | null) => void;
  onSelectArea: (area: Area | null) => void;
  disabled?: boolean;
}

export default function ComplexSearch({
  selectedComplex,
  selectedArea,
  onSelectComplex,
  onSelectArea,
  disabled,
}: ComplexSearchProps) {
  const [query, setQuery] = useState<string>('');
  const [results, setResults] = useState<Complex[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [open, setOpen] = useState<boolean>(false);
  const [areas, setAreas] = useState<Area[]>([]);
  const debounceRef = useRef<number | null>(null);

  // 디바운스 검색
  useEffect(() => {
    if (selectedComplex) return; // 이미 선택된 상태면 검색 안 함
    if (!query || query.length < 2) {
      setResults([]);
      return;
    }
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(async () => {
      setLoading(true);
      try {
        const res = await complexesApi.list({ search: query, limit: 10 });
        setResults(res.items);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [query, selectedComplex]);

  // 단지 선택 시 평형 목록 로드
  useEffect(() => {
    if (!selectedComplex) {
      setAreas([]);
      return;
    }
    let cancelled = false;
    complexesApi
      .listAreas(selectedComplex.id)
      .then((data) => {
        if (!cancelled) setAreas(data);
      })
      .catch(() => {
        if (!cancelled) setAreas([]);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedComplex]);

  const handlePick = (c: Complex) => {
    onSelectComplex(c);
    onSelectArea(null);
    setQuery(c.name);
    setOpen(false);
    setResults([]);
  };

  const handleClear = () => {
    onSelectComplex(null);
    onSelectArea(null);
    setQuery('');
    setResults([]);
    setAreas([]);
  };

  return (
    <div className="complex-search">
      <div className="apply-field">
        <label>단지 검색 *</label>
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            value={query}
            placeholder="단지명 입력 (예: 은마아파트)"
            onChange={(e) => {
              setQuery(e.target.value);
              if (selectedComplex) onSelectComplex(null);
            }}
            onFocus={() => results.length > 0 && setOpen(true)}
            onBlur={() => window.setTimeout(() => setOpen(false), 150)}
            disabled={disabled}
            style={{ width: '100%' }}
          />
          {selectedComplex && (
            <button
              type="button"
              onClick={handleClear}
              disabled={disabled}
              style={{
                position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                background: 'transparent', border: 'none', color: '#666',
                cursor: 'pointer', fontSize: 18,
              }}
              aria-label="단지 선택 해제"
            >
              ×
            </button>
          )}
          {open && !selectedComplex && (results.length > 0 || loading) && (
            <ul className="complex-search-results" style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
              background: 'white', border: '1px solid #ccc', borderRadius: 4,
              maxHeight: 240, overflowY: 'auto', listStyle: 'none',
              margin: 0, padding: 0, boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            }}>
              {loading && <li style={{ padding: '8px 12px', color: '#999' }}>검색 중…</li>}
              {!loading && results.map((c) => (
                <li
                  key={c.id}
                  onMouseDown={() => handlePick(c)}
                  style={{ padding: '8px 12px', cursor: 'pointer', borderBottom: '1px solid #eee' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#f5f5f5')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'white')}
                >
                  <div style={{ fontWeight: 500 }}>{c.name}</div>
                  <div style={{ fontSize: 12, color: '#666' }}>{c.address}</div>
                </li>
              ))}
              {!loading && results.length === 0 && (
                <li style={{ padding: '8px 12px', color: '#999' }}>검색 결과가 없습니다.</li>
              )}
            </ul>
          )}
        </div>
        {selectedComplex && (
          <div style={{ marginTop: 4, fontSize: 12, color: '#006FBD' }}>
            선택: <strong>{selectedComplex.name}</strong> ({selectedComplex.address})
          </div>
        )}
      </div>

      {selectedComplex && (
        <div className="apply-field">
          <label>평형 *</label>
          <select
            value={selectedArea?.id ?? ''}
            onChange={(e) => {
              const id = parseInt(e.target.value, 10);
              const a = areas.find((x) => x.id === id) ?? null;
              onSelectArea(a);
            }}
            disabled={disabled || areas.length === 0}
            className="duration-select"
          >
            <option value="">선택하세요</option>
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                전용 {a.exclusive_m2.toFixed(0)}㎡{a.pyeong ? ` (${Math.round(a.pyeong)}평)` : ''}
              </option>
            ))}
          </select>
          {areas.length === 0 && (
            <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
              평형 정보가 등록되지 않은 단지입니다.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
