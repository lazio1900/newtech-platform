/**
 * 관리자 패널 — 서브탭(사용자 / LLM 연결).
 * 사용자 메뉴에서 "관리자 패널" 진입 시 표시.
 */
import { useState } from 'react';
import AdminUsers from './AdminUsers';
import AdminLlmConnections from './AdminLlmConnections';
import AdminPrompts from './AdminPrompts';
import AdminDbConnections from './AdminDbConnections';
import './AdminPanel.css';

type SubTab = 'users' | 'llm' | 'prompts' | 'db';

export default function AdminPanel() {
  const [sub, setSub] = useState<SubTab>('users');

  return (
    <div className="admin-panel">
      <header className="admin-panel-header">
        <h2>관리자 패널</h2>
      </header>

      <nav className="admin-subnav">
        <SubTabBtn label="사용자" active={sub === 'users'} onClick={() => setSub('users')} />
        <SubTabBtn label="LLM 연결" active={sub === 'llm'} onClick={() => setSub('llm')} />
        <SubTabBtn label="프롬프트" active={sub === 'prompts'} onClick={() => setSub('prompts')} />
        <SubTabBtn label="DB 연결" active={sub === 'db'} onClick={() => setSub('db')} />
      </nav>

      <div className="admin-panel-body">
        {sub === 'users' && <AdminUsers />}
        {sub === 'llm' && <AdminLlmConnections />}
        {sub === 'prompts' && <AdminPrompts />}
        {sub === 'db' && <AdminDbConnections />}
      </div>
    </div>
  );
}

function SubTabBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`admin-subnav-btn ${active ? 'active' : ''}`}
    >
      {label}
    </button>
  );
}
