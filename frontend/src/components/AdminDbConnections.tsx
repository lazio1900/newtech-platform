/**
 * DB 연결 관리 — endpoint 목록 + 테스트 + 기본 지정.
 * 베이스라인 UI 톤 (AdminLlmConnections 와 동일).
 */
import { useCallback, useEffect, useState } from 'react';
import {
  adminDbApi,
  type DbConnection,
  type DbConnectionCreatePayload,
  type DbConnectionUpdatePayload,
  type DbTestResult,
} from '../api/adminDb';
import './AdminDbConnections.css';

type DialogMode = null | 'create' | 'edit';

export default function AdminDbConnections() {
  const [items, setItems] = useState<DbConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<DbConnection | null>(null);
  const [testResults, setTestResults] = useState<Record<number, DbTestResult & { testing?: boolean }>>({});

  const fetchList = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const list = await adminDbApi.list();
      setItems(list);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '목록 조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const handleSetDefault = async (c: DbConnection) => {
    if (c.is_default) return;
    try {
      await adminDbApi.setDefault(c.id);
      fetchList();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(e?.response?.data?.detail || e?.message || '기본 설정 실패');
    }
  };

  const handleDelete = async (c: DbConnection) => {
    if (!confirm(`정말 '${c.name}' 연결을 삭제하시겠습니까?`)) return;
    try {
      await adminDbApi.remove(c.id);
      fetchList();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(e?.response?.data?.detail || e?.message || '삭제 실패');
    }
  };

  const handleTest = async (c: DbConnection) => {
    setTestResults((prev) => ({ ...prev, [c.id]: { ok: false, testing: true } }));
    try {
      const res = await adminDbApi.test(c.id);
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
    <div className="db-conn">
      <div className="db-conn-header">
        <div>
          <h3>DB 연결</h3>
          <p>관리용 endpoint 등록·테스트. 실제 backend 가 사용하는 DATABASE_URL 은 .env 기반이며, 변경은 재시작 시점에 반영됩니다.</p>
        </div>
        <button className="db-btn-primary" onClick={() => { setTarget(null); setDialog('create'); }}>
          + 연결 추가
        </button>
      </div>

      <div className="db-conn-warning">
        ⚠ 운영 중에는 backend DB 연결을 즉시 갈아끼우지 않습니다. 이 화면은 endpoint 정보 관리·테스트 용도입니다.
      </div>

      {error && <div className="db-conn-error">{error}</div>}

      {loading && items.length === 0 && (
        <div className="db-conn-empty">로딩 중...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="db-conn-empty">
          등록된 DB 연결이 없습니다. "+ 연결 추가" 로 시작하세요.
        </div>
      )}

      <div className="db-conn-list">
        {items.map((c) => {
          const t = testResults[c.id];
          return (
            <div key={c.id} className={`db-card ${!c.is_active ? 'inactive' : ''}`}>
              <div className="db-card-main">
                <div className="db-card-head">
                  <span className="db-card-name">{c.name}</span>
                  {c.is_default && <span className="db-pill db-pill-default">기본</span>}
                  <span className={`db-pill ${c.is_active ? 'db-pill-active' : 'db-pill-inactive'}`}>
                    {c.is_active ? '활성' : '비활성'}
                  </span>
                  <span className="db-pill db-pill-driver">{c.driver}</span>
                </div>
                <dl className="db-card-meta">
                  <div><dt>Host</dt><dd>{c.host}:{c.port}</dd></div>
                  <div><dt>DB</dt><dd>{c.database}</dd></div>
                  <div><dt>User</dt><dd>{c.username}</dd></div>
                  <div><dt>Password</dt><dd>{c.password_masked || <span className="db-muted">미설정</span>}</dd></div>
                </dl>
                {t && (
                  <div className={`db-test-result ${t.ok ? 'ok' : 'err'}`}>
                    {t.testing ? '테스트 중...' :
                      t.ok ? `✓ 성공 — ${t.latency_ms}ms` :
                      `✗ 실패 — ${t.error || '알 수 없음'}`}
                  </div>
                )}
              </div>
              <div className="db-card-actions">
                <button className="db-btn-ghost" onClick={() => handleTest(c)} disabled={!!t?.testing}>
                  {t?.testing ? '테스트 중...' : '테스트'}
                </button>
                {!c.is_default && (
                  <button className="db-btn-ghost" onClick={() => handleSetDefault(c)}>
                    기본으로
                  </button>
                )}
                <button className="db-btn-ghost" onClick={() => { setTarget(c); setDialog('edit'); }}>
                  수정
                </button>
                <button className="db-btn-ghost-danger" onClick={() => handleDelete(c)}>
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
  target?: DbConnection;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(target?.name || '');
  const [host, setHost] = useState(target?.host || '');
  const [port, setPort] = useState<string>(String(target?.port || 5432));
  const [database, setDatabase] = useState(target?.database || '');
  const [username, setUsername] = useState(target?.username || '');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [isActive, setIsActive] = useState(target?.is_active ?? true);
  const [setDefault, setSetDefault] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSaving(true); setError(null);
    try {
      if (mode === 'create') {
        const payload: DbConnectionCreatePayload = {
          name: name.trim(),
          driver: 'postgresql',
          host: host.trim(),
          port: parseInt(port, 10) || 5432,
          database: database.trim(),
          username: username.trim(),
          password: password || null,
          is_active: isActive,
          set_default: setDefault,
        };
        await adminDbApi.create(payload);
      } else if (target) {
        const payload: DbConnectionUpdatePayload = {
          name: name.trim(),
          host: host.trim(),
          port: parseInt(port, 10) || 5432,
          database: database.trim(),
          username: username.trim(),
          password: password,
          is_active: isActive,
        };
        await adminDbApi.update(target.id, payload);
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
    <div className="db-dialog-backdrop" onClick={onClose}>
      <div className="db-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="db-dialog-title">{mode === 'create' ? 'DB 연결 추가' : `연결 수정: ${target?.name}`}</h3>
        <div className="db-dialog-body">
          <Field label="이름 *" hint="예: '운영 PostgreSQL', '분석 DW'">
            <input className="db-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </Field>
          <div className="db-row">
            <Field label="Host *">
              <input className="db-input" value={host} onChange={(e) => setHost(e.target.value)}
                     placeholder="postgres.example.com" maxLength={200} />
            </Field>
            <Field label="Port *">
              <input className="db-input" type="number" value={port} onChange={(e) => setPort(e.target.value)}
                     min={1} max={65535} />
            </Field>
          </div>
          <div className="db-row">
            <Field label="Database *">
              <input className="db-input" value={database} onChange={(e) => setDatabase(e.target.value)}
                     placeholder="kb_estate" maxLength={120} />
            </Field>
            <Field label="User *">
              <input className="db-input" value={username} onChange={(e) => setUsername(e.target.value)}
                     placeholder="kb_user" maxLength={120} />
            </Field>
          </div>
          <Field label={mode === 'edit' ? 'Password (변경 시에만 입력)' : 'Password'}
                 hint="평문 저장됨. 비워두면 (수정 모드) 기존 값 유지">
            <div style={{ display: 'flex', gap: 8 }}>
              <input className="db-input" type={showPw ? 'text' : 'password'}
                     value={password} onChange={(e) => setPassword(e.target.value)}
                     maxLength={500} placeholder={mode === 'edit' ? '비워두면 기존 비번 유지' : ''}
                     style={{ flex: 1 }} />
              <button type="button" className="db-btn-ghost" onClick={() => setShowPw((v) => !v)}>
                {showPw ? '숨김' : '표시'}
              </button>
            </div>
          </Field>

          <div className="db-checkbox-row">
            <label>
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> 활성
            </label>
            {mode === 'create' && (
              <label>
                <input type="checkbox" checked={setDefault} onChange={(e) => setSetDefault(e.target.checked)} /> 추가 후 기본으로 지정
              </label>
            )}
          </div>
          {error && <div className="db-dialog-error">{error}</div>}
        </div>
        <div className="db-dialog-footer">
          <button className="db-btn-ghost" onClick={onClose} disabled={saving}>취소</button>
          <button
            className="db-btn-primary"
            onClick={handleSubmit}
            disabled={saving || !name.trim() || !host.trim() || !database.trim() || !username.trim()}
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
    <div className="db-field">
      <label className="db-field-label">{label}</label>
      {children}
      {hint && <div className="db-field-hint">{hint}</div>}
    </div>
  );
}
