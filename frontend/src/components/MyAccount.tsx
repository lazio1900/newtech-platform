/**
 * 본인 계정 — 프로필 수정 + 비밀번호 변경.
 * Settings 의 "계정 정보" 서브탭에서 임베드되어 표시됨.
 */
import { useState } from 'react';
import { accountApi } from '../api/account';
import './MyAccount.css';

interface MyAccountProps {
  user: {
    user_id: string;
    role?: string;
    company_name?: string | null;
    ceo_name?: string | null;
    business_number?: string | null;
    phone?: string | null;
  };
  onProfileUpdated?: () => void;
}

const ROLE_LABEL: Record<string, string> = {
  admin: '관리자',
  auditor: '심사역',
  customer: '대부업체',
};

export default function MyAccount({ user, onProfileUpdated }: MyAccountProps) {
  const [companyName, setCompanyName] = useState(user.company_name || '');
  const [ceoName, setCeoName] = useState(user.ceo_name || '');
  const [businessNumber, setBusinessNumber] = useState(user.business_number || '');
  const [phone, setPhone] = useState(user.phone || '');
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPwConfirm, setNewPwConfirm] = useState('');
  const [pwSaving, setPwSaving] = useState(false);
  const [pwMsg, setPwMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const handleProfileSave = async () => {
    setProfileSaving(true);
    setProfileMsg(null);
    try {
      await accountApi.updateProfile({
        company_name: companyName,
        ceo_name: ceoName,
        business_number: businessNumber,
        phone,
      });
      setProfileMsg({ ok: true, text: '프로필이 저장되었습니다.' });
      onProfileUpdated?.();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setProfileMsg({ ok: false, text: e?.response?.data?.detail || e?.message || '저장 실패' });
    } finally {
      setProfileSaving(false);
    }
  };

  const handlePasswordSave = async () => {
    if (newPw !== newPwConfirm) {
      setPwMsg({ ok: false, text: '새 비밀번호가 일치하지 않습니다.' });
      return;
    }
    if (newPw.length < 4) {
      setPwMsg({ ok: false, text: '새 비밀번호는 4자 이상이어야 합니다.' });
      return;
    }
    setPwSaving(true);
    setPwMsg(null);
    try {
      await accountApi.changePassword(currentPw, newPw);
      setPwMsg({ ok: true, text: '비밀번호가 변경되었습니다.' });
      setCurrentPw(''); setNewPw(''); setNewPwConfirm('');
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setPwMsg({ ok: false, text: e?.response?.data?.detail || e?.message || '변경 실패' });
    } finally {
      setPwSaving(false);
    }
  };

  const displayName = user.ceo_name || user.company_name || user.user_id;
  const initial = (displayName?.[0] || '?').toUpperCase();
  const roleLabel = ROLE_LABEL[user.role || ''] || user.role || '-';

  return (
    <div className="my-account">
      {/* 사용자 헤더 카드 */}
      <section className="ma-card ma-header-card">
        <div className="ma-avatar" aria-hidden>{initial}</div>
        <div className="ma-header-info">
          <div className="ma-display-name">{displayName}</div>
          <div className="ma-meta">
            <span className="ma-id">@{user.user_id}</span>
            <span className="ma-role-pill" data-role={user.role || 'customer'}>{roleLabel}</span>
          </div>
        </div>
      </section>

      {/* 프로필 카드 */}
      <section className="ma-card">
        <header className="ma-card-header">
          <h3>프로필</h3>
          <p>회사 정보와 연락처를 관리합니다.</p>
        </header>
        <div className="ma-form-grid">
          <Field label="회사명">
            <input
              className="ma-input"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
              maxLength={200}
              placeholder="예: 파란캐피탈대부"
            />
          </Field>
          <Field label="대표자">
            <input
              className="ma-input"
              value={ceoName}
              onChange={(e) => setCeoName(e.target.value)}
              maxLength={80}
            />
          </Field>
          <Field label="사업자번호">
            <input
              className="ma-input"
              value={businessNumber}
              onChange={(e) => setBusinessNumber(e.target.value)}
              maxLength={40}
              placeholder="000-00-00000"
            />
          </Field>
          <Field label="연락처">
            <input
              className="ma-input"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              maxLength={40}
              placeholder="010-0000-0000"
            />
          </Field>
        </div>
        <footer className="ma-card-footer">
          {profileMsg && (
            <span className={`ma-msg ${profileMsg.ok ? 'ok' : 'err'}`}>{profileMsg.text}</span>
          )}
          <button
            className="ma-btn-primary"
            onClick={handleProfileSave}
            disabled={profileSaving}
          >
            {profileSaving ? '저장 중...' : '프로필 저장'}
          </button>
        </footer>
      </section>

      {/* 비밀번호 카드 */}
      <section className="ma-card">
        <header className="ma-card-header">
          <h3>비밀번호 변경</h3>
          <p>새 비밀번호는 최소 4자 이상이어야 합니다.</p>
        </header>
        <div className="ma-form-stack">
          <Field label="현재 비밀번호">
            <input
              className="ma-input"
              type="password"
              value={currentPw}
              onChange={(e) => setCurrentPw(e.target.value)}
              maxLength={200}
              autoComplete="current-password"
            />
          </Field>
          <Field label="새 비밀번호">
            <input
              className="ma-input"
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              maxLength={200}
              autoComplete="new-password"
            />
          </Field>
          <Field label="새 비밀번호 확인">
            <input
              className="ma-input"
              type="password"
              value={newPwConfirm}
              onChange={(e) => setNewPwConfirm(e.target.value)}
              maxLength={200}
              autoComplete="new-password"
            />
          </Field>
        </div>
        <footer className="ma-card-footer">
          {pwMsg && (
            <span className={`ma-msg ${pwMsg.ok ? 'ok' : 'err'}`}>{pwMsg.text}</span>
          )}
          <button
            className="ma-btn-primary"
            onClick={handlePasswordSave}
            disabled={pwSaving || !currentPw || !newPw || !newPwConfirm}
          >
            {pwSaving ? '변경 중...' : '비밀번호 변경'}
          </button>
        </footer>
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="ma-field">
      <label className="ma-field-label">{label}</label>
      {children}
    </div>
  );
}
