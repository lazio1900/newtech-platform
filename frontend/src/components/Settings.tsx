/**
 * 설정 컨테이너 — 서브탭(계정 정보 / 화면 인터페이스).
 * AuditorDashboard 에서 사용자 메뉴 → 설정 진입.
 */
import { useState } from 'react';
import MyAccount from './MyAccount';
import InterfaceSettings from './InterfaceSettings';

type SubTab = 'account' | 'interface';

interface SettingsProps {
  user: {
    user_id: string;
    role?: string;
    company_name?: string | null;
    ceo_name?: string | null;
    business_number?: string | null;
    phone?: string | null;
  };
}

export default function Settings({ user }: SettingsProps) {
  const [sub, setSub] = useState<SubTab>('account');

  return (
    <div style={{ padding: 24 }}>
      <h2 style={{ marginBottom: 16 }}>설정</h2>

      {/* 서브탭 */}
      <div style={{ display: 'flex', gap: 4, borderBottom: '1px solid #E5E7EB', marginBottom: 20 }}>
        <SubTabBtn label="계정 정보" active={sub === 'account'} onClick={() => setSub('account')} />
        <SubTabBtn label="화면 인터페이스" active={sub === 'interface'} onClick={() => setSub('interface')} />
      </div>

      {sub === 'account' && <MyAccount user={user} />}
      {sub === 'interface' && <InterfaceSettings />}
    </div>
  );
}

function SubTabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: '10px 16px',
        background: 'transparent',
        border: 'none',
        borderBottom: active ? '2px solid #006FBD' : '2px solid transparent',
        color: active ? '#006FBD' : '#6B7785',
        fontSize: 14,
        fontWeight: active ? 700 : 500,
        cursor: 'pointer',
        marginBottom: -1,
      }}
    >
      {label}
    </button>
  );
}
