/**
 * 프롬프트 관리 — LLM 기능별 system prompt (+ rights 의 critique) 편집.
 *
 * - 좌측: feature 리스트 (라벨 + 설명 + override 배지)
 * - 우측: 선택한 feature 의 prompt 편집기
 *   - prompt_key 가 여러 개면 탭 형태
 *   - 텍스트 영역 + 저장 / 기본값으로 복원 / 기본값 보기 토글
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { adminPromptsApi, type PromptItem } from '../api/adminPrompts';
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
  // override 가 있으면 그 content, 없으면 default 로 시작
  const initial = item.content ?? item.default_content ?? '';
  const [text, setText] = useState(initial);
  const [showDefault, setShowDefault] = useState(false);
  const [state, setState] = useState<SaveState>({});
  const dirty = text !== initial;

  // editor state 리셋은 부모의 key prop 으로 컴포넌트 리마운트 시 자동 처리됨.

  const handleSave = async () => {
    setState({ saving: true });
    try {
      await adminPromptsApi.upsert(item.feature_key, item.prompt_key, text);
      setState({ msg: { ok: true, text: '저장되었습니다. 다음 호출부터 적용됩니다.' } });
      onSaved();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '저장 실패' } });
    }
  };

  const handleReset = async () => {
    if (!item.has_override) return;
    if (!confirm('사용자 정의 프롬프트를 삭제하고 기본값으로 복원합니다. 계속하시겠습니까?')) return;
    setState({ saving: true });
    try {
      await adminPromptsApi.reset(item.feature_key, item.prompt_key);
      setState({ msg: { ok: true, text: '기본값으로 복원됐습니다.' } });
      onReset();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setState({ msg: { ok: false, text: e?.response?.data?.detail || e?.message || '복원 실패' } });
    }
  };

  return (
    <section className="prompts-editor">
      <header className="prompts-editor-header">
        <div>
          <div className="prompts-editor-title">
            {item.feature_label} · {item.prompt_label}
            {item.has_override && <span className="prompts-pill-override">사용자 정의</span>}
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
            {state.saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </footer>
    </section>
  );
}
