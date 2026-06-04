/**
 * 관리자 패널 — 서브탭(사용자 / LLM 연결 / 프롬프트 / DB 연결 / 데이터 매핑 / 운영 전환).
 */
import { useState } from 'react';
import AdminUsers from './AdminUsers';
import AdminLlmConnections from './AdminLlmConnections';
import AdminPrompts from './AdminPrompts';
import AdminDbConnections from './AdminDbConnections';
import AdminDataMappings from './AdminDataMappings';
import AdminMigrationCheck from './AdminMigrationCheck';
import './AdminPanel.css';

type SubTab = 'users' | 'llm' | 'prompts' | 'db' | 'data-mappings' | 'migration';

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
        <SubTabBtn label="데이터 매핑" active={sub === 'data-mappings'} onClick={() => setSub('data-mappings')} />
        <SubTabBtn label="운영 전환" active={sub === 'migration'} onClick={() => setSub('migration')} />
      </nav>

      <div className="admin-panel-body">
        {sub === 'users' && <AdminUsers />}
        {sub === 'llm' && <AdminLlmConnections />}
        {sub === 'prompts' && <AdminPrompts />}
        {sub === 'db' && <AdminDbConnections />}
        {sub === 'data-mappings' && <AdminDataMappings />}
        {sub === 'migration' && (
          <AdminMigrationCheck onNavigate={(t) => setSub(t)} />
        )}
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
