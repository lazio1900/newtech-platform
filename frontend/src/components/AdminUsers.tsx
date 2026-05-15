/**
 * 관리자용 사용자 관리 — 목록·검색·생성·수정·비번 reset·비활성화.
 * admin role 만 접근.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  adminUsersApi,
  type AdminUser,
  type AdminUserCreatePayload,
  type AdminUserUpdatePayload,
  type UserRole,
} from '../api/account';

type DialogMode = null | 'create' | 'edit' | 'reset-password';

export default function AdminUsers() {
  const [items, setItems] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<UserRole | ''>('');
  const [activeFilter, setActiveFilter] = useState<'' | 'true' | 'false'>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<AdminUser | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await adminUsersApi.list({
        search: search.trim() || undefined,
        role: roleFilter || undefined,
        is_active: activeFilter === '' ? undefined : activeFilter === 'true',
        page,
        page_size: pageSize,
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '목록 조회 실패');
    } finally {
      setLoading(false);
    }
  }, [search, roleFilter, activeFilter, page]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16 }}>사용자</h3>
        <button onClick={() => { setTarget(null); setDialog('create'); }} style={btnPrimary}>
          + 사용자 추가
        </button>
      </div>

      {/* 검색·필터 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          placeholder="ID·회사명·대표자 검색"
          style={{ padding: '6px 10px', minWidth: 220 }}
        />
        <select value={roleFilter} onChange={(e) => { setRoleFilter(e.target.value as UserRole | ''); setPage(1); }} style={selectStyle}>
          <option value="">전체 권한</option>
          <option value="customer">customer</option>
          <option value="auditor">auditor</option>
          <option value="admin">admin</option>
        </select>
        <select value={activeFilter} onChange={(e) => { setActiveFilter(e.target.value as '' | 'true' | 'false'); setPage(1); }} style={selectStyle}>
          <option value="">전체 상태</option>
          <option value="true">활성</option>
          <option value="false">비활성</option>
        </select>
        <span style={{ color: '#6B7785', fontSize: 13, marginLeft: 'auto' }}>총 {total}건</span>
      </div>

      {error && (
        <div style={{ padding: 12, background: '#FEE2E2', color: '#991B1B', borderRadius: 6, marginBottom: 12 }}>
          {error}
        </div>
      )}

      <table className="app-table" style={{ width: '100%', fontSize: 13 }}>
        <thead>
          <tr>
            <th>ID</th>
            <th>권한</th>
            <th>회사명</th>
            <th>대표자</th>
            <th>연락처</th>
            <th>상태</th>
            <th>최근 로그인</th>
            <th>액션</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24 }}>로딩 중...</td></tr>
          )}
          {!loading && items.length === 0 && (
            <tr><td colSpan={8} style={{ textAlign: 'center', padding: 24, color: '#6B7785' }}>사용자가 없습니다.</td></tr>
          )}
          {!loading && items.map((u) => (
            <tr key={u.user_id}>
              <td style={{ fontFamily: 'monospace' }}>{u.user_id}</td>
              <td>
                <RoleSelect
                  value={u.role}
                  onChange={(next) => handleInlineRoleChange(u, next, fetchList)}
                />
              </td>
              <td>{u.company_name || '-'}</td>
              <td>{u.ceo_name || '-'}</td>
              <td>{u.phone || '-'}</td>
              <td>
                <ActiveBadge
                  active={u.is_active}
                  onClick={() => handleInlineActiveToggle(u, fetchList)}
                />
              </td>
              <td style={{ fontSize: 11, color: '#6B7785' }}>{u.last_login_at?.replace('T', ' ').slice(0, 16) || '-'}</td>
              <td>
                <button onClick={() => { setTarget(u); setDialog('edit'); }} style={btnSmall}>수정</button>{' '}
                <button onClick={() => { setTarget(u); setDialog('reset-password'); }} style={btnSmall}>비번 reset</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {totalPages > 1 && (
        <div style={{ marginTop: 16, display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center' }}>
          <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={btnSmall}>이전</button>
          <span style={{ fontSize: 13 }}>{page} / {totalPages}</span>
          <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={btnSmall}>다음</button>
        </div>
      )}

      {dialog === 'create' && (
        <UserFormDialog
          mode="create"
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); fetchList(); }}
        />
      )}
      {dialog === 'edit' && target && (
        <UserFormDialog
          mode="edit"
          target={target}
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); fetchList(); }}
        />
      )}
      {dialog === 'reset-password' && target && (
        <ResetPasswordDialog
          target={target}
          onClose={() => setDialog(null)}
          onDone={() => setDialog(null)}
        />
      )}
    </div>
  );
}


async function handleInlineRoleChange(u: AdminUser, next: UserRole, refresh: () => void) {
  if (u.role === next) return;
  if (!confirm(`'${u.user_id}' 권한을 ${u.role} → ${next} 로 변경하시겠습니까?`)) return;
  try {
    await adminUsersApi.update(u.user_id, { role: next });
    refresh();
  } catch (err) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string };
    alert(e?.response?.data?.detail || e?.message || '권한 변경 실패');
    refresh();
  }
}

async function handleInlineActiveToggle(u: AdminUser, refresh: () => void) {
  const nextActive = !u.is_active;
  const label = nextActive ? '활성화' : '비활성화';
  if (!confirm(`'${u.user_id}' 를 ${label} 하시겠습니까?`)) return;
  try {
    if (nextActive) {
      await adminUsersApi.update(u.user_id, { is_active: true });
    } else {
      await adminUsersApi.deactivate(u.user_id);
    }
    refresh();
  } catch (err) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string };
    alert(e?.response?.data?.detail || e?.message || `${label} 실패`);
  }
}


const ROLE_STYLE: Record<UserRole, { bg: string; color: string; border: string }> = {
  admin:    { bg: '#FEE2E2', color: '#991B1B', border: '#FCA5A5' },
  auditor:  { bg: '#DBEAFE', color: '#1E40AF', border: '#93C5FD' },
  customer: { bg: '#F3F4F6', color: '#374151', border: '#D1D5DB' },
};

function RoleSelect({ value, onChange }: { value: UserRole; onChange: (next: UserRole) => void }) {
  const s = ROLE_STYLE[value];
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as UserRole)}
      style={{
        padding: '3px 8px', borderRadius: 999,
        background: s.bg, color: s.color, border: `1px solid ${s.border}`,
        fontSize: 11, fontWeight: 600, cursor: 'pointer',
      }}
    >
      <option value="customer">customer</option>
      <option value="auditor">auditor</option>
      <option value="admin">admin</option>
    </select>
  );
}


function ActiveBadge({ active, onClick }: { active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={active ? '클릭하여 비활성화' : '클릭하여 활성화'}
      style={{
        padding: '2px 10px', borderRadius: 999, fontSize: 11, fontWeight: 600,
        background: active ? '#D1FAE5' : '#E5E7EB',
        color: active ? '#065F46' : '#6B7280',
        border: `1px solid ${active ? '#86EFAC' : '#D1D5DB'}`,
        cursor: 'pointer',
      }}
    >
      {active ? '활성' : '비활성'}
    </button>
  );
}


function UserFormDialog({ mode, target, onClose, onSaved }: {
  mode: 'create' | 'edit';
  target?: AdminUser;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [userId, setUserId] = useState(target?.user_id || '');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<UserRole>(target?.role || 'customer');
  const [isActive, setIsActive] = useState(target?.is_active ?? true);
  const [companyName, setCompanyName] = useState(target?.company_name || '');
  const [ceoName, setCeoName] = useState(target?.ceo_name || '');
  const [businessNumber, setBusinessNumber] = useState(target?.business_number || '');
  const [phone, setPhone] = useState(target?.phone || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSaving(true); setError(null);
    try {
      if (mode === 'create') {
        const payload: AdminUserCreatePayload = {
          user_id: userId.trim(),
          password,
          role,
          company_name: companyName || null,
          ceo_name: ceoName || null,
          business_number: businessNumber || null,
          phone: phone || null,
        };
        await adminUsersApi.create(payload);
      } else if (target) {
        const payload: AdminUserUpdatePayload = {
          role,
          is_active: isActive,
          company_name: companyName,
          ceo_name: ceoName,
          business_number: businessNumber,
          phone,
        };
        await adminUsersApi.update(target.user_id, payload);
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
    <DialogShell title={mode === 'create' ? '사용자 추가' : `사용자 수정: ${target?.user_id}`} onClose={onClose}>
      <Row label="로그인 ID *">
        <input value={userId} onChange={(e) => setUserId(e.target.value)} disabled={mode === 'edit'} maxLength={80} />
      </Row>
      {mode === 'create' && (
        <Row label="초기 비밀번호 *">
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} maxLength={200} />
        </Row>
      )}
      <Row label="권한 *">
        <select value={role} onChange={(e) => setRole(e.target.value as UserRole)} style={selectStyle}>
          <option value="customer">customer</option>
          <option value="auditor">auditor</option>
          <option value="admin">admin</option>
        </select>
      </Row>
      {mode === 'edit' && (
        <Row label="활성 상태">
          <label style={{ fontSize: 13 }}>
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> 활성
          </label>
        </Row>
      )}
      <Row label="회사명"><input value={companyName} onChange={(e) => setCompanyName(e.target.value)} maxLength={200} /></Row>
      <Row label="대표자"><input value={ceoName} onChange={(e) => setCeoName(e.target.value)} maxLength={80} /></Row>
      <Row label="사업자번호"><input value={businessNumber} onChange={(e) => setBusinessNumber(e.target.value)} maxLength={40} /></Row>
      <Row label="연락처"><input value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={40} /></Row>

      {error && <div style={{ color: '#991B1B', fontSize: 13, marginTop: 8 }}>{error}</div>}

      <div style={{ marginTop: 16, textAlign: 'right' }}>
        <button onClick={onClose} disabled={saving} style={{ ...btnSmall, marginRight: 8 }}>취소</button>
        <button
          onClick={handleSubmit}
          disabled={saving || !userId.trim() || (mode === 'create' && !password)}
          style={btnPrimary}
        >
          {saving ? '저장 중...' : '저장'}
        </button>
      </div>
    </DialogShell>
  );
}


function ResetPasswordDialog({ target, onClose, onDone }: {
  target: AdminUser;
  onClose: () => void;
  onDone: () => void;
}) {
  const [newPw, setNewPw] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const handleSubmit = async () => {
    if (newPw.length < 4) { setError('4자 이상 입력해주세요.'); return; }
    setSaving(true); setError(null);
    try {
      await adminUsersApi.resetPassword(target.user_id, newPw);
      setDone(true);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || 'reset 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <DialogShell title={`비밀번호 reset: ${target.user_id}`} onClose={onClose}>
      {!done ? (
        <>
          <Row label="새 비밀번호">
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} maxLength={200} />
          </Row>
          <div style={{ fontSize: 12, color: '#6B7785', marginTop: 4 }}>
            사용자에게 이 비밀번호를 안내하세요. 이후 본인이 직접 변경 가능합니다.
          </div>
          {error && <div style={{ color: '#991B1B', fontSize: 13, marginTop: 8 }}>{error}</div>}
          <div style={{ marginTop: 16, textAlign: 'right' }}>
            <button onClick={onClose} disabled={saving} style={{ ...btnSmall, marginRight: 8 }}>취소</button>
            <button onClick={handleSubmit} disabled={saving || newPw.length < 4} style={btnPrimary}>
              {saving ? 'reset 중...' : 'reset'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div style={{ padding: 12, background: '#D1FAE5', color: '#065F46', borderRadius: 6, marginBottom: 12 }}>
            비밀번호가 성공적으로 변경되었습니다. 새 비밀번호: <strong>{newPw}</strong>
          </div>
          <div style={{ textAlign: 'right' }}>
            <button onClick={onDone} style={btnPrimary}>확인</button>
          </div>
        </>
      )}
    </DialogShell>
  );
}


function DialogShell({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: '#fff', borderRadius: 8, padding: 24, minWidth: 480, maxWidth: 600,
        maxHeight: '90vh', overflowY: 'auto',
      }}>
        <h3 style={{ margin: '0 0 16px 0' }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}


function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 10, display: 'grid', gridTemplateColumns: '120px 1fr', alignItems: 'center', gap: 8 }}>
      <label style={{ fontSize: 13, color: '#374151' }}>{label}</label>
      <div>{children}</div>
    </div>
  );
}


const btnPrimary: React.CSSProperties = {
  padding: '8px 16px', background: '#006FBD', color: '#fff',
  border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer',
};
const btnSmall: React.CSSProperties = {
  padding: '4px 10px', background: '#F3F4F6', color: '#374151',
  border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 12, cursor: 'pointer',
};
const selectStyle: React.CSSProperties = {
  padding: '6px 10px', border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 13,
};
