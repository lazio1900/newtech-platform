/**
 * LLM 연결 관리 — OpenAI 호환 endpoint 등록·테스트·기본 지정.
 * OpenWebUI 의 Connections 패널 스타일 참고.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  adminLlmApi,
  type LlmConnection,
  type LlmConnectionCreatePayload,
  type LlmConnectionUpdatePayload,
  type LlmTestResult,
} from '../api/adminLlm';
import './AdminLlmConnections.css';

type DialogMode = null | 'create' | 'edit';

export default function AdminLlmConnections() {
  const [items, setItems] = useState<LlmConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<LlmConnection | null>(null);
  const [testResults, setTestResults] = useState<Record<number, LlmTestResult & { testing?: boolean }>>({});

  const fetchList = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const list = await adminLlmApi.list();
      setItems(list);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '목록 조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleSetDefault = async (c: LlmConnection) => {
    if (c.is_default) return;
    try {
      await adminLlmApi.setDefault(c.id);
      fetchList();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(e?.response?.data?.detail || e?.message || '기본 설정 실패');
    }
  };

  const handleDelete = async (c: LlmConnection) => {
    if (!confirm(`정말 '${c.name}' 연결을 삭제하시겠습니까?`)) return;
    try {
      await adminLlmApi.remove(c.id);
      fetchList();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(e?.response?.data?.detail || e?.message || '삭제 실패');
    }
  };

  const handleTest = async (c: LlmConnection) => {
    setTestResults((prev) => ({ ...prev, [c.id]: { ok: false, testing: true } }));
    try {
      const res = await adminLlmApi.test(c.id);
      setTestResults((prev) => ({ ...prev, [c.id]: { ...res, testing: false } }));
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setTestResults((prev) => ({
        ...prev,
        [c.id]: { ok: false, error: e?.response?.data?.detail || e?.message || '테스트 실패', testing: false },
      }));
    }
  };

  return (
    <div className="llm-conn">
      <div className="llm-conn-header">
        <div>
          <h3>LLM 연결</h3>
          <p>OpenAI 호환 endpoint 를 등록하면 분석에 사용됩니다. 한 개를 기본으로 지정하세요.</p>
        </div>
        <button className="llm-btn-primary" onClick={() => { setTarget(null); setDialog('create'); }}>
          + 연결 추가
        </button>
      </div>

      {error && <div className="llm-conn-error">{error}</div>}

      {loading && items.length === 0 && (
        <div className="llm-conn-empty">로딩 중...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="llm-conn-empty">
          등록된 LLM 연결이 없습니다. "+ 연결 추가" 로 시작하세요.
        </div>
      )}

      <div className="llm-conn-list">
        {items.map((c) => {
          const t = testResults[c.id];
          return (
            <div key={c.id} className={`llm-card ${!c.is_active ? 'inactive' : ''}`}>
              <div className="llm-card-main">
                <div className="llm-card-head">
                  <span className="llm-card-name">{c.name}</span>
                  {c.is_default && <span className="llm-pill llm-pill-default">기본</span>}
                  <span className={`llm-pill ${c.is_active ? 'llm-pill-active' : 'llm-pill-inactive'}`}>
                    {c.is_active ? '활성' : '비활성'}
                  </span>
                  <span className="llm-pill llm-pill-provider">{c.provider}</span>
                </div>
                <dl className="llm-card-meta">
                  <div><dt>모델</dt><dd>{c.default_model}</dd></div>
                  <div><dt>Base URL</dt><dd>{c.base_url || <span className="llm-muted">기본 (api.openai.com)</span>}</dd></div>
                  <div><dt>API Key</dt><dd>{c.api_key_masked || <span className="llm-muted">미설정</span>}</dd></div>
                </dl>
                {t && (
                  <div className={`llm-test-result ${t.ok ? 'ok' : 'err'}`}>
                    {t.testing ? '테스트 중...' :
                      t.ok ? `✓ 성공 — model=${t.model}, ${t.latency_ms}ms` :
                      `✗ 실패 — ${t.error || '알 수 없음'}`}
                  </div>
                )}
              </div>
              <div className="llm-card-actions">
                <button className="llm-btn-ghost" onClick={() => handleTest(c)} disabled={!!t?.testing}>
                  {t?.testing ? '테스트 중...' : '테스트'}
                </button>
                {!c.is_default && (
                  <button className="llm-btn-ghost" onClick={() => handleSetDefault(c)}>
                    기본으로
                  </button>
                )}
                <button className="llm-btn-ghost" onClick={() => { setTarget(c); setDialog('edit'); }}>
                  수정
                </button>
                <button className="llm-btn-ghost-danger" onClick={() => handleDelete(c)}>
                  삭제
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {dialog === 'create' && (
        <ConnectionDialog
          mode="create"
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); fetchList(); }}
        />
      )}
      {dialog === 'edit' && target && (
        <ConnectionDialog
          mode="edit"
          target={target}
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); fetchList(); }}
        />
      )}
    </div>
  );
}


function ConnectionDialog({ mode, target, onClose, onSaved }: {
  mode: 'create' | 'edit';
  target?: LlmConnection;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(target?.name || '');
  const [baseUrl, setBaseUrl] = useState(target?.base_url || '');
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [defaultModel, setDefaultModel] = useState(target?.default_model || 'gpt-4o-mini');
  const [isActive, setIsActive] = useState(target?.is_active ?? true);
  const [setDefault, setSetDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSaving(true); setError(null);
    try {
      if (mode === 'create') {
        const payload: LlmConnectionCreatePayload = {
          name: name.trim(),
          provider: 'openai',
          base_url: baseUrl.trim() || null,
          api_key: apiKey.trim() || null,
          default_model: defaultModel.trim(),
          is_active: isActive,
          set_default: setDefault,
        };
        await adminLlmApi.create(payload);
      } else if (target) {
        const payload: LlmConnectionUpdatePayload = {
          name: name.trim(),
          base_url: baseUrl.trim() || null,
          api_key: apiKey,           // 빈 문자열이면 backend 가 미변경 처리
          default_model: defaultModel.trim(),
          is_active: isActive,
        };
        await adminLlmApi.update(target.id, payload);
      }
      onSaved();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '저장 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="llm-dialog-backdrop" onClick={onClose}>
      <div className="llm-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="llm-dialog-title">{mode === 'create' ? 'LLM 연결 추가' : `연결 수정: ${target?.name}`}</h3>
        <div className="llm-dialog-body">
          <Field label="이름 *" hint="UI 표시용. 예: '기본 OpenAI', 'Azure 사내'">
            <input className="llm-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </Field>
          <Field label="Base URL" hint="비워두면 OpenAI 기본 (https://api.openai.com/v1)">
            <input className="llm-input" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} maxLength={500}
                   placeholder="https://api.openai.com/v1" />
          </Field>
          <Field label={mode === 'edit' ? 'API Key (변경 시에만 입력)' : 'API Key *'} hint="평문 저장됨">
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                className="llm-input"
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                maxLength={500}
                placeholder={mode === 'edit' ? '비워두면 기존 키 유지' : 'sk-...'}
                style={{ flex: 1 }}
              />
              <button type="button" className="llm-btn-ghost" onClick={() => setShowKey((v) => !v)}>
                {showKey ? '숨김' : '표시'}
              </button>
            </div>
          </Field>
          <Field label="기본 모델 *" hint="이 연결로 호출할 때 사용할 모델 ID">
            <input className="llm-input" value={defaultModel} onChange={(e) => setDefaultModel(e.target.value)}
                   maxLength={200} placeholder="gpt-4o-mini" />
          </Field>
          <div className="llm-checkbox-row">
            <label>
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> 활성
            </label>
            {mode === 'create' && (
              <label>
                <input type="checkbox" checked={setDefault} onChange={(e) => setSetDefault(e.target.checked)} /> 추가 후 기본으로 지정
              </label>
            )}
          </div>
          {error && <div className="llm-dialog-error">{error}</div>}
        </div>
        <div className="llm-dialog-footer">
          <button className="llm-btn-ghost" onClick={onClose} disabled={saving}>취소</button>
          <button
            className="llm-btn-primary"
            onClick={handleSubmit}
            disabled={saving || !name.trim() || !defaultModel.trim() || (mode === 'create' && !apiKey.trim())}
          >
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}


function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="llm-field">
      <label className="llm-field-label">{label}</label>
      {children}
      {hint && <div className="llm-field-hint">{hint}</div>}
    </div>
  );
}
