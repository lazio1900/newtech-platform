/**
 * 프롬프트 관리 — LLM 기능별 system prompt (+ rights 의 critique) 편집.
 *
 * - 좌측: feature 리스트 (라벨 + 설명 + override 배지)
 * - 우측: 선택한 feature 의 prompt 편집기
 *   - prompt_key 가 여러 개면 탭 형태
 *   - 텍스트 영역 + 저장 / 기본값으로 복원 / 기본값 보기 토글
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminPromptsApi, type PromptItem, type PromptVersion, type PromptTestResult, type PromptSample } from '../api/adminPrompts';
import './AdminPrompts.css';

interface SaveState {
  saving?: boolean;
  msg?: { ok: boolean; text: string } | null;
}

export default function AdminPrompts() {
  const [items, setItems] = useState<PromptItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const list = await adminPromptsApi.list();
      setItems(list);
      if (list.length > 0 && !selectedKey) {
        setSelectedKey(`${list[0].feature_key}/${list[0].prompt_key}`);
      }
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '목록 조회 실패');
    } finally {
      setLoading(false);
    }
  }, [selectedKey]);

  useEffect(() => { fetchList(); }, [fetchList]);

  // feature 별로 grouping
  const featureGroups = useMemo(() => {
    const groups: Record<string, { meta: PromptItem; keys: PromptItem[] }> = {};
    for (const it of items) {
      if (!groups[it.feature_key]) {
        groups[it.feature_key] = { meta: it, keys: [] };
      }
      groups[it.feature_key].keys.push(it);
    }
    return Object.values(groups);
  }, [items]);

  const selected = items.find((i) => `${i.feature_key}/${i.prompt_key}` === selectedKey) || null;

  return (
    <div className="prompts">
      <div className="prompts-header">
        <h3>프롬프트 관리</h3>
        <p>LLM 시스템 프롬프트를 기능별로 편집합니다. 저장하지 않으면 코드 기본값이 사용됩니다.</p>
      </div>

      {error && <div className="prompts-error">{error}</div>}

      {loading && items.length === 0 && (
        <div className="prompts-empty">로딩 중...</div>
      )}

      {!loading && items.length > 0 && (
        <div className="prompts-layout">
          <aside className="prompts-nav">
            {featureGroups.map((g) => (
              <div key={g.meta.feature_key} className="prompts-nav-group">
                <div className="prompts-nav-group-title">{g.meta.feature_label}</div>
                {g.keys.map((p) => {
                  const key = `${p.feature_key}/${p.prompt_key}`;
                  const isActive = key === selectedKey;
                  return (
                    <button
                      key={key}
                      onClick={() => setSelectedKey(key)}
                      className={`prompts-nav-item ${isActive ? 'active' : ''}`}
                    >
                      <span className="prompts-nav-item-label">{p.prompt_label}</span>
                      {p.has_override && <span className="prompts-pill-override">사용자 정의</span>}
                    </button>
                  );
                })}
              </div>
            ))}
          </aside>

          <main className="prompts-editor-wrap">
            {selected && (
              <PromptEditor
                key={`${selected.feature_key}/${selected.prompt_key}/${selected.has_override}/${selected.updated_at ?? ''}`}
                item={selected}
                onSaved={fetchList}
                onReset={fetchList}
              />
            )}
          </main>
        </div>
      )}
    </div>
  );
}


function PromptEditor({ item, onSaved, onReset }: {
  item: PromptItem;
  onSaved: () => void;
  onReset: () => void;
}) {
  const initial = item.content ?? item.default_content ?? '';
  const [text, setText] = useState(initial);
  const [showDefault, setShowDefault] = useState(false);
  const [state, setState] = useState<SaveState>({});
  const dirty = text !== initial;

  // 버전 이력
  const [showHistory, setShowHistory] = useState(false);
  const [versions, setVersions] = useState<PromptVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [detailVersion, setDetailVersion] = useState<PromptVersion | null>(null);

  // 테스트
  const [showTest, setShowTest] = useState(false);
  const [testInput, setTestInput] = useState('');
  const [testJsonMode, setTestJsonMode] = useState(false);
  const [testRunning, setTestRunning] = useState(false);
  const [testResult, setTestResult] = useState<PromptTestResult | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [samples, setSamples] = useState<PromptSample[]>([]);
  const [selectedSampleIdx, setSelectedSampleIdx] = useState<number>(-1);

  const loadVersions = useCallback(async () => {
    setVersionsLoading(true);
    try {
      const list = await adminPromptsApi.versions(item.feature_key, item.prompt_key);
      setVersions(list);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '버전 조회 실패' } });
    } finally {
      setVersionsLoading(false);
    }
  }, [item.feature_key, item.prompt_key]);

  useEffect(() => {
    if (showHistory) loadVersions();
  }, [showHistory, loadVersions]);

  // 테스트 열 때 샘플 목록 로드
  useEffect(() => {
    if (!showTest) return;
    adminPromptsApi.samples(item.feature_key, item.prompt_key)
      .then(setSamples)
      .catch(() => setSamples([]));
  }, [showTest, item.feature_key, item.prompt_key]);

  const applySample = (idx: number) => {
    setSelectedSampleIdx(idx);
    if (idx < 0) return;
    const s = samples[idx];
    if (s) {
      setTestInput(s.user_input);
      setTestJsonMode(!!s.json_mode);
    }
  };

  const handleSave = async () => {
    setState({ saving: true });
    try {
      await adminPromptsApi.upsert(item.feature_key, item.prompt_key, text);
      setState({ msg: { ok: true, text: '새 버전으로 저장되었습니다. 다음 호출부터 적용됩니다.' } });
      onSaved();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '저장 실패' } });
    }
  };

  const handleReset = async () => {
    if (!item.has_override) return;
    if (!confirm('현재 활성 버전을 비활성화하고 기본값으로 돌아갑니다. 과거 버전은 보존됩니다. 계속할까요?')) return;
    setState({ saving: true });
    try {
      await adminPromptsApi.reset(item.feature_key, item.prompt_key);
      setState({ msg: { ok: true, text: '기본값으로 복원됐습니다 (과거 버전 보존).' } });
      onReset();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '복원 실패' } });
    }
  };

  const handleActivate = async (v: number) => {
    if (!confirm(`v${v} 를 활성 버전으로 되돌릴까요?`)) return;
    setState({ saving: true });
    try {
      await adminPromptsApi.activate(item.feature_key, item.prompt_key, v);
      setState({ msg: { ok: true, text: `v${v} 가 활성화됐습니다.` } });
      onSaved();
      await loadVersions();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '활성화 실패' } });
    }
  };

  const handleTest = async () => {
    if (!text.trim()) { alert('프롬프트 내용이 비어 있습니다.'); return; }
    if (!testInput.trim()) { alert('샘플 입력을 작성해주세요.'); return; }
    setTestRunning(true);
    setTestError(null);
    setTestResult(null);
    try {
      const r = await adminPromptsApi.test(text, testInput, testJsonMode);
      setTestResult(r);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setTestError(e?.response?.data?.detail || e?.message || '테스트 실패');
    } finally {
      setTestRunning(false);
    }
  };

  return (
    <section className="prompts-editor">
      <header className="prompts-editor-header">
        <div>
          <div className="prompts-editor-title">
            {item.feature_label} · {item.prompt_label}
            {item.has_override && item.version != null && (
              <span className="prompts-pill-override">v{item.version} · 활성</span>
            )}
            {!item.has_override && <span className="prompts-pill-override" style={{ background: '#9CA3AF' }}>기본값</span>}
          </div>
          <p className="prompts-editor-desc">{item.prompt_description}</p>
        </div>
        <div className="prompts-editor-toggle">
          <label>
            <input
              type="checkbox"
              checked={showDefault}
              onChange={(e) => setShowDefault(e.target.checked)}
            />{' '}
            기본값 보기
          </label>
        </div>
      </header>

      {showDefault ? (
        <pre className="prompts-default-view">{item.default_content || '(기본값 없음)'}</pre>
      ) : (
        <textarea
          className="prompts-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
        />
      )}

      <footer className="prompts-editor-footer">
        {item.updated_at && (
          <span className="prompts-meta">
            마지막 수정: {item.updated_at.replace('T', ' ').slice(0, 16)}
            {item.updated_by && ` (${item.updated_by})`}
          </span>
        )}
        {state.msg && (
          <span className={`prompts-msg ${state.msg.ok ? 'ok' : 'err'}`}>{state.msg.text}</span>
        )}
        <div className="prompts-editor-actions">
          <button
            className="prompts-btn-ghost-danger"
            style={{ background: '#fff', borderColor: '#9CA3AF', color: '#374151' }}
            onClick={() => setShowHistory((s) => !s)}
            disabled={state.saving}
          >
            {showHistory ? '버전 이력 닫기' : '버전 이력'}
          </button>
          <button
            className="prompts-btn-ghost-danger"
            style={{ background: '#fff', borderColor: '#006FBD', color: '#006FBD' }}
            onClick={() => setShowTest((s) => !s)}
            disabled={state.saving}
          >
            {showTest ? '테스트 닫기' : '테스트 실행'}
          </button>
          {item.has_override && (
            <button className="prompts-btn-ghost-danger" onClick={handleReset} disabled={state.saving}>
              기본값으로 복원
            </button>
          )}
          <button
            className="prompts-btn-primary"
            onClick={handleSave}
            disabled={!dirty || state.saving || showDefault}
          >
            {state.saving ? '저장 중...' : '새 버전으로 저장'}
          </button>
        </div>
      </footer>

      {showHistory && (
        <div style={{ marginTop: 16, border: '1px solid #E5E7EB', borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#051C48', marginBottom: 8 }}>버전 이력</div>
          {versionsLoading ? (
            <div style={{ color: '#9CA3AF', fontSize: 13 }}>불러오는 중...</div>
          ) : versions.length === 0 ? (
            <div style={{ color: '#9CA3AF', fontSize: 13 }}>버전 이력이 없습니다.</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#F9FAFB' }}>
                  <th style={{ padding: 8, textAlign: 'left', width: 60 }}>버전</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 80 }}>상태</th>
                  <th style={{ padding: 8, textAlign: 'left' }}>본문 (앞 120자)</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 140 }}>수정 시각</th>
                  <th style={{ padding: 8, textAlign: 'left', width: 90 }}>수정자</th>
                  <th style={{ padding: 8, width: 100 }}></th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v) => (
                  <tr key={v.id} style={{ borderTop: '1px solid #F3F4F6' }}>
                    <td style={{ padding: 8, fontWeight: 600 }}>v{v.version}</td>
                    <td style={{ padding: 8 }}>
                      {v.is_active ? (
                        <span style={{ background: '#20c997', color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700 }}>활성</span>
                      ) : '–'}
                    </td>
                    <td style={{ padding: 8, color: '#6B7280' }}>
                      {v.content.slice(0, 120)}{v.content.length > 120 ? '…' : ''}
                    </td>
                    <td style={{ padding: 8, color: '#6B7280' }}>{v.updated_at ?? '-'}</td>
                    <td style={{ padding: 8, color: '#6B7280' }}>{v.updated_by ?? '-'}</td>
                    <td style={{ padding: 8, textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button
                        onClick={() => setDetailVersion(v)}
                        style={{ padding: '4px 10px', fontSize: 12, background: '#fff', color: '#374151', border: '1px solid #D1D5DB', borderRadius: 4, cursor: 'pointer', marginRight: 4 }}
                      >
                        상세
                      </button>
                      {!v.is_active && (
                        <button
                          onClick={() => handleActivate(v.version)}
                          disabled={state.saving}
                          style={{ padding: '4px 10px', fontSize: 12, background: '#fff', color: '#006FBD', border: '1px solid #006FBD', borderRadius: 4, cursor: 'pointer' }}
                        >
                          활성화
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {detailVersion && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 24,
          }}
          onClick={() => setDetailVersion(null)}
        >
          <div
            style={{ background: '#fff', borderRadius: 8, width: 900, maxWidth: '94vw', maxHeight: '90vh', display: 'flex', flexDirection: 'column' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #E5E7EB', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: 16, fontWeight: 700, color: '#051C48' }}>
                  v{detailVersion.version} 상세
                  {detailVersion.is_active && (
                    <span style={{ marginLeft: 8, background: '#20c997', color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700 }}>활성</span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>
                  수정: {detailVersion.updated_at ?? '-'} · {detailVersion.updated_by ?? '-'}
                </div>
              </div>
              <button
                onClick={() => setDetailVersion(null)}
                style={{ background: 'transparent', border: 'none', fontSize: 20, color: '#9CA3AF', cursor: 'pointer' }}
                aria-label="닫기"
              >✕</button>
            </div>
            <pre style={{
              flex: 1, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              padding: 16, margin: 0, fontSize: 13, lineHeight: 1.55, fontFamily: 'inherit',
              background: '#F9FAFB',
            }}>
              {detailVersion.content}
            </pre>
            <div style={{ padding: '12px 20px', borderTop: '1px solid #E5E7EB', display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(detailVersion.content).catch(() => {});
                }}
                style={{ padding: '6px 14px', fontSize: 13, background: '#fff', color: '#374151', border: '1px solid #D1D5DB', borderRadius: 4, cursor: 'pointer' }}
              >
                전체 복사
              </button>
              {!detailVersion.is_active && (
                <button
                  onClick={() => {
                    const v = detailVersion.version;
                    setDetailVersion(null);
                    handleActivate(v);
                  }}
                  style={{ padding: '6px 14px', fontSize: 13, background: '#006FBD', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontWeight: 600 }}
                >
                  이 버전으로 복구
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {showTest && (
        <div style={{ marginTop: 16, border: '1px solid #E5E7EB', borderRadius: 8, padding: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: '#051C48', marginBottom: 8 }}>
            테스트 실행 — 현재 편집기의 본문이 system, 아래 입력이 user 로 LLM 호출됩니다.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
            <label style={{ fontSize: 13, color: '#374151' }}>샘플:</label>
            <select
              value={selectedSampleIdx}
              onChange={(e) => applySample(parseInt(e.target.value, 10))}
              style={{ padding: '6px 10px', border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 13, minWidth: 220 }}
            >
              <option value={-1}>{samples.length === 0 ? '— 등록된 샘플 없음 —' : '— 직접 입력 —'}</option>
              {samples.map((s, i) => (
                <option key={i} value={i}>{s.label}</option>
              ))}
            </select>
            <label style={{ fontSize: 13, color: '#374151', marginLeft: 12 }}>
              <input type="checkbox" checked={testJsonMode} onChange={(e) => setTestJsonMode(e.target.checked)} />{' '}
              json_mode
            </label>
            <span style={{ fontSize: 11, color: '#9CA3AF' }}>
              샘플은 backend/utils/prompt_samples.py 에서 관리
            </span>
          </div>
          <textarea
            value={testInput}
            onChange={(e) => { setTestInput(e.target.value); setSelectedSampleIdx(-1); }}
            placeholder="LLM 에게 보낼 user 입력 (샘플 선택 또는 직접 작성)"
            style={{
              width: '100%', minHeight: 120, padding: 8, fontSize: 13,
              border: '1px solid #D1D5DB', borderRadius: 4, boxSizing: 'border-box', fontFamily: 'inherit',
            }}
            spellCheck={false}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
            <button
              className="prompts-btn-primary"
              onClick={handleTest}
              disabled={testRunning}
            >
              {testRunning ? '실행 중... (최대 2분)' : '실행'}
            </button>
          </div>

          {testError && (
            <div style={{ marginTop: 12, padding: 10, background: '#FEE2E2', color: '#991B1B', borderRadius: 4, fontSize: 13 }}>
              {testError}
            </div>
          )}
          {testResult && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, color: '#6B7280', marginBottom: 6 }}>
                모델: <strong>{testResult.model ?? '-'}</strong>{' · '}
                응답: <strong>{testResult.elapsed_ms}ms</strong>{' · '}
                tokens: <strong>{testResult.prompt_tokens ?? '-'} → {testResult.completion_tokens ?? '-'}</strong>{' · '}
                finish: {testResult.finish_reason ?? '-'}
              </div>
              <pre style={{
                whiteSpace: 'pre-wrap', background: '#F9FAFB', padding: 12, borderRadius: 4,
                border: '1px solid #E5E7EB', maxHeight: 300, overflowY: 'auto', fontSize: 12,
              }}>
                {testResult.text}
              </pre>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
