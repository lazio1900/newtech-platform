import { useEffect, useState, useCallback } from 'react';
import { lendersApi, type Lender, type LenderInput, type YearlyFinancial } from '@/api/lenders';

type EditState =
  | { mode: 'create' }
  | { mode: 'edit'; lender: Lender }
  | { mode: 'closed' };

interface FinRow {
  year: string;
  assets: string;
  liabilities: string;
  equity: string;
  revenue: string;
  operating_profit: string;
  net_income: string;
}

interface FormState {
  company_name: string;
  business_number: string;
  ceo_name: string;
  credit_score_nice: string;
  credit_score_kcb: string;
  direct_debt: string;
  guarantee_debt: string;
  financial: [FinRow, FinRow, FinRow];
}

const emptyFinRow = (year: number): FinRow => ({
  year: String(year),
  assets: '',
  liabilities: '',
  equity: '',
  revenue: '',
  operating_profit: '',
  net_income: '',
});

const emptyForm = (): FormState => {
  const y = new Date().getFullYear();
  return {
    company_name: '',
    business_number: '',
    ceo_name: '',
    credit_score_nice: '',
    credit_score_kcb: '',
    direct_debt: '',
    guarantee_debt: '',
    financial: [emptyFinRow(y - 2), emptyFinRow(y - 1), emptyFinRow(y)],
  };
};

const parseScore = (raw: string): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0 || n > 1000) return null;
  return Math.round(n);
};

const parseInt0 = (raw: string): number | null => {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const n = Number(trimmed.replace(/,/g, ''));
  if (!Number.isFinite(n)) return null;
  return Math.round(n);
};

export default function LendersPanel() {
  const [items, setItems] = useState<Lender[]>([]);
  const [query, setQuery] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditState>({ mode: 'closed' });
  const [form, setForm] = useState<FormState>(emptyForm());
  const [submitting, setSubmitting] = useState<boolean>(false);

  const fetchItems = useCallback(async (q?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await lendersApi.list(q?.trim() || undefined);
      setItems(data);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      setError(err?.response?.data?.detail || err?.message || '대부업체 조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchItems(); }, [fetchItems]);

  const openCreate = () => {
    setForm(emptyForm());
    setEdit({ mode: 'create' });
  };

  const openEdit = (lender: Lender) => {
    const y = new Date().getFullYear();
    const fromLender: FinRow[] = (lender.financial_data ?? []).slice(0, 3).map((f) => ({
      year: String(f.year ?? ''),
      assets: f.assets != null ? String(f.assets) : '',
      liabilities: f.liabilities != null ? String(f.liabilities) : '',
      equity: f.equity != null ? String(f.equity) : '',
      revenue: f.revenue != null ? String(f.revenue) : '',
      operating_profit: f.operating_profit != null ? String(f.operating_profit) : '',
      net_income: f.net_income != null ? String(f.net_income) : '',
    }));
    while (fromLender.length < 3) fromLender.push(emptyFinRow(y - (2 - fromLender.length)));
    setForm({
      company_name: lender.company_name,
      business_number: lender.business_number ?? '',
      ceo_name: lender.ceo_name ?? '',
      credit_score_nice: lender.credit_score_nice != null ? String(lender.credit_score_nice) : '',
      credit_score_kcb: lender.credit_score_kcb != null ? String(lender.credit_score_kcb) : '',
      direct_debt: lender.direct_debt != null ? String(lender.direct_debt) : '',
      guarantee_debt: lender.guarantee_debt != null ? String(lender.guarantee_debt) : '',
      financial: [fromLender[0], fromLender[1], fromLender[2]],
    });
    setEdit({ mode: 'edit', lender });
  };

  const closeEdit = () => {
    setEdit({ mode: 'closed' });
    setForm(emptyForm());
  };

  const updateFinCell = (rowIdx: number, key: keyof FinRow, value: string) => {
    setForm((prev) => {
      const next = [...prev.financial] as [FinRow, FinRow, FinRow];
      next[rowIdx] = { ...next[rowIdx], [key]: value };
      return { ...prev, financial: next };
    });
  };

  const handleSubmit = async () => {
    if (!form.company_name.trim()) { alert('대부업체 명칭을 입력해주세요.'); return; }
    if (form.credit_score_nice.trim() && parseScore(form.credit_score_nice) === null) {
      alert('NICE 신용점수는 0~1000 사이 정수로 입력해주세요.'); return;
    }
    if (form.credit_score_kcb.trim() && parseScore(form.credit_score_kcb) === null) {
      alert('KCB 신용점수는 0~1000 사이 정수로 입력해주세요.'); return;
    }

    const financial: YearlyFinancial[] = [];
    for (const row of form.financial) {
      const year = parseInt0(row.year);
      const others = [row.assets, row.liabilities, row.equity, row.revenue, row.operating_profit, row.net_income];
      const hasAny = year != null || others.some((s) => s.trim());
      if (!hasAny) continue;
      if (year == null) { alert('재무 표의 연도를 입력해주세요.'); return; }
      financial.push({
        year,
        assets: parseInt0(row.assets),
        liabilities: parseInt0(row.liabilities),
        equity: parseInt0(row.equity),
        revenue: parseInt0(row.revenue),
        operating_profit: parseInt0(row.operating_profit),
        net_income: parseInt0(row.net_income),
      });
    }

    const payload: LenderInput = {
      company_name: form.company_name.trim(),
      business_number: form.business_number.trim() || null,
      ceo_name: form.ceo_name.trim() || null,
      credit_score_nice: parseScore(form.credit_score_nice),
      credit_score_kcb: parseScore(form.credit_score_kcb),
      direct_debt: parseInt0(form.direct_debt),
      guarantee_debt: parseInt0(form.guarantee_debt),
      financial_data: financial.length > 0 ? financial : null,
    };

    setSubmitting(true);
    try {
      if (edit.mode === 'create') {
        await lendersApi.create(payload);
      } else if (edit.mode === 'edit') {
        await lendersApi.update(edit.lender.id, payload);
      }
      closeEdit();
      await fetchItems(query);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      alert(err?.response?.data?.detail || err?.message || '저장 실패');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (lender: Lender) => {
    if (!window.confirm(`'${lender.company_name}' 을(를) 삭제하시겠습니까?`)) return;
    try {
      await lendersApi.remove(lender.id);
      await fetchItems(query);
    } catch (e) {
      const err = e as { response?: { data?: { detail?: string } }; message?: string };
      alert(err?.response?.data?.detail || err?.message || '삭제 실패');
    }
  };

  const styles = {
    wrap: { padding: 24, maxWidth: 1100, margin: '0 auto' } as const,
    head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 } as const,
    title: { fontSize: 20, fontWeight: 700, color: '#051C48', margin: 0 } as const,
    toolbar: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 } as const,
    input: { padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 14, minWidth: 260 } as const,
    primaryBtn: { padding: '8px 16px', background: '#006FBD', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600 } as const,
    secondaryBtn: { padding: '6px 12px', background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 6, cursor: 'pointer', fontSize: 13 } as const,
    dangerBtn: { padding: '6px 12px', background: '#fff', color: '#EF5350', border: '1px solid #EF5350', borderRadius: 6, cursor: 'pointer', fontSize: 13 } as const,
    table: { width: '100%', borderCollapse: 'collapse' as const, background: '#fff', border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' } as const,
    th: { textAlign: 'left' as const, padding: '10px 12px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', fontSize: 13, color: '#6b7280', fontWeight: 600 } as const,
    td: { padding: '10px 12px', borderBottom: '1px solid #f3f4f6', fontSize: 14 } as const,
    empty: { padding: 24, textAlign: 'center' as const, color: '#9CA3AF' } as const,
    backdrop: { position: 'fixed' as const, inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 },
    modal: { background: '#fff', borderRadius: 8, padding: 24, width: 880, maxWidth: '94vw', maxHeight: '90vh', overflowY: 'auto' as const } as const,
    modalTitle: { fontSize: 18, fontWeight: 700, color: '#051C48', margin: '0 0 16px 0' } as const,
    sectionTitle: { fontSize: 14, fontWeight: 700, color: '#051C48', margin: '16px 0 8px 0' } as const,
    field: { marginBottom: 12 } as const,
    label: { display: 'block', fontSize: 13, color: '#374151', marginBottom: 4, fontWeight: 500 } as const,
    grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 } as const,
    grid3: { display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 12 } as const,
    finTable: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 13 } as const,
    finTh: { padding: '6px 8px', background: '#f9fafb', borderBottom: '1px solid #e5e7eb', textAlign: 'left' as const, color: '#6b7280', fontWeight: 600 } as const,
    finCell: { padding: '4px', borderBottom: '1px solid #f3f4f6' } as const,
    finInput: { width: '100%', padding: '6px 8px', border: '1px solid #d1d5db', borderRadius: 4, fontSize: 13, boxSizing: 'border-box' as const } as const,
    actions: { display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 } as const,
  };

  const FIN_COLS: Array<{ key: keyof FinRow; label: string; width?: string }> = [
    { key: 'year', label: '연도', width: '70px' },
    { key: 'assets', label: '자산' },
    { key: 'liabilities', label: '부채' },
    { key: 'equity', label: '자본' },
    { key: 'revenue', label: '매출' },
    { key: 'operating_profit', label: '영업이익' },
    { key: 'net_income', label: '당기순이익' },
  ];

  return (
    <div style={styles.wrap}>
      <div style={styles.head}>
        <h2 style={styles.title}>대부업체 등록</h2>
        <button type="button" onClick={openCreate} style={styles.primaryBtn}>+ 신규 등록</button>
      </div>

      <div style={styles.toolbar}>
        <input
          style={styles.input}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="명칭 또는 사업자번호로 검색"
          onKeyDown={(e) => { if (e.key === 'Enter') fetchItems(query); }}
        />
        <button type="button" onClick={() => fetchItems(query)} style={styles.secondaryBtn}>검색</button>
        {query && (
          <button type="button" onClick={() => { setQuery(''); fetchItems(); }} style={styles.secondaryBtn}>전체</button>
        )}
      </div>

      {error && <div style={{ color: '#EF5350', marginBottom: 12 }}>{error}</div>}

      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>대부업체 명칭</th>
            <th style={styles.th}>사업자번호</th>
            <th style={styles.th}>대표자명</th>
            <th style={styles.th}>NICE</th>
            <th style={styles.th}>KCB</th>
            <th style={{ ...styles.th, width: 160 }}>액션</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={6} style={styles.empty}>불러오는 중...</td></tr>
          ) : items.length === 0 ? (
            <tr><td colSpan={6} style={styles.empty}>등록된 대부업체가 없습니다. 우측 상단 '신규 등록' 으로 추가하세요.</td></tr>
          ) : items.map((row) => (
            <tr key={row.id}>
              <td style={styles.td}><strong>{row.company_name}</strong></td>
              <td style={styles.td}>{row.business_number ?? '-'}</td>
              <td style={styles.td}>{row.ceo_name ?? '-'}</td>
              <td style={styles.td}>{row.credit_score_nice ?? '-'}</td>
              <td style={styles.td}>{row.credit_score_kcb ?? '-'}</td>
              <td style={styles.td}>
                <button type="button" onClick={() => openEdit(row)} style={{ ...styles.secondaryBtn, marginRight: 6 }}>수정</button>
                <button type="button" onClick={() => handleDelete(row)} style={styles.dangerBtn}>삭제</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {edit.mode !== 'closed' && (
        <div style={styles.backdrop} onClick={closeEdit}>
          <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3 style={styles.modalTitle}>{edit.mode === 'create' ? '대부업체 신규 등록' : '대부업체 수정'}</h3>

            <div style={styles.grid3}>
              <div style={styles.field}>
                <label style={styles.label}>대부업체 명칭 *</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="text" value={form.company_name} maxLength={200}
                  onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                  disabled={submitting}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>사업자등록번호</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="text" value={form.business_number} maxLength={20}
                  onChange={(e) => setForm({ ...form, business_number: e.target.value })}
                  placeholder="예: 123-45-67890" disabled={submitting}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>대표자명</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="text" value={form.ceo_name} maxLength={80}
                  onChange={(e) => setForm({ ...form, ceo_name: e.target.value })}
                  disabled={submitting}
                />
              </div>
            </div>

            <div style={styles.grid2}>
              <div style={styles.field}>
                <label style={styles.label}>대표자 신용점수 (NICE)</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="number" value={form.credit_score_nice} min={0} max={1000}
                  onChange={(e) => setForm({ ...form, credit_score_nice: e.target.value })}
                  placeholder="0~1000" disabled={submitting}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>대표자 신용점수 (KCB)</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="number" value={form.credit_score_kcb} min={0} max={1000}
                  onChange={(e) => setForm({ ...form, credit_score_kcb: e.target.value })}
                  placeholder="0~1000" disabled={submitting}
                />
              </div>
            </div>

            <h4 style={styles.sectionTitle}>채무 정보 (원)</h4>
            <div style={styles.grid2}>
              <div style={styles.field}>
                <label style={styles.label}>직접채무</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="number" value={form.direct_debt} min={0}
                  onChange={(e) => setForm({ ...form, direct_debt: e.target.value })}
                  placeholder="원" disabled={submitting}
                />
              </div>
              <div style={styles.field}>
                <label style={styles.label}>보증채무</label>
                <input
                  style={{ ...styles.input, width: '100%', minWidth: 0 }}
                  type="number" value={form.guarantee_debt} min={0}
                  onChange={(e) => setForm({ ...form, guarantee_debt: e.target.value })}
                  placeholder="원" disabled={submitting}
                />
              </div>
            </div>

            <h4 style={styles.sectionTitle}>최근 3개년 재무 정보 (원)</h4>
            <table style={styles.finTable}>
              <thead>
                <tr>
                  {FIN_COLS.map((c) => (
                    <th key={c.key} style={{ ...styles.finTh, width: c.width }}>{c.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {form.financial.map((row, idx) => (
                  <tr key={idx}>
                    {FIN_COLS.map((c) => (
                      <td key={c.key} style={styles.finCell}>
                        <input
                          style={styles.finInput}
                          type="number"
                          value={row[c.key]}
                          onChange={(e) => updateFinCell(idx, c.key, e.target.value)}
                          disabled={submitting}
                          placeholder={c.key === 'year' ? 'YYYY' : ''}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginTop: 4 }}>
              빈 행은 무시됩니다. 한 행이라도 입력하면 연도는 필수입니다.
            </div>

            <div style={styles.actions}>
              <button type="button" onClick={closeEdit} style={styles.secondaryBtn} disabled={submitting}>취소</button>
              <button type="button" onClick={handleSubmit} style={styles.primaryBtn} disabled={submitting}>
                {submitting ? '저장 중...' : '저장'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
