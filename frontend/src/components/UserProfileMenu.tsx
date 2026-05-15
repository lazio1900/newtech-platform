/**
 * 사이드바 하단 사용자 프로필 메뉴 (OpenWebUI 스타일).
 * 사용자 아이콘 + 이름 단일 버튼 → 클릭 시 드롭다운으로 설정·관리자 패널·로그아웃 노출.
 */
import { useEffect, useRef, useState } from 'react';
import './UserProfileMenu.css';

interface UserProfileMenuProps {
  user: {
    user_id: string;
    role?: string;
    company_name?: string;
    ceo_name?: string;
  };
  onOpenAccount: () => void;
  onOpenAdminPanel: () => void;
  onLogout: () => void;
}

export default function UserProfileMenu({ user, onOpenAccount, onOpenAdminPanel, onLogout }: UserProfileMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  // 바깥 클릭 시 드롭다운 닫기
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const displayName = user.ceo_name || user.company_name || user.user_id;
  const initial = (displayName?.[0] || '?').toUpperCase();
  const isAdmin = user.role === 'admin';

  return (
    <div className="user-profile-menu" ref={rootRef}>
      <button
        className={`user-profile-btn ${open ? 'open' : ''}`}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="user-profile-avatar" aria-hidden>
          {/* SVG 인물 아이콘 */}
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm0 2c-3.6 0-8 1.8-8 5.2V21h16v-1.8c0-3.4-4.4-5.2-8-5.2Z" />
          </svg>
        </span>
        <span className="user-profile-name" title={user.user_id}>{displayName}</span>
        <span className="user-profile-caret" aria-hidden>▾</span>
        <span className="sr-only">{initial}</span>
      </button>

      {open && (
        <div className="user-profile-dropdown" role="menu">
          <button
            className="user-menu-item"
            role="menuitem"
            onClick={() => { setOpen(false); onOpenAccount(); }}
          >
            <span className="user-menu-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M19.4 15a1.7 1.7 0 0 0 .4 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.4 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.4l-.1.1A2 2 0 1 1 4.2 17l.1-.1a1.7 1.7 0 0 0 .4-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.4-1.9l-.1-.1A2 2 0 1 1 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.4 1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.4l.1-.1A2 2 0 1 1 19.8 7l-.1.1a1.7 1.7 0 0 0-.4 1.9 1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1ZM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z" />
              </svg>
            </span>
            설정
          </button>

          {isAdmin && (
            <button
              className="user-menu-item"
              role="menuitem"
              onClick={() => { setOpen(false); onOpenAdminPanel(); }}
            >
              <span className="user-menu-icon" aria-hidden>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                  <path d="M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v4H3V6Zm0 6h18v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6Zm4 2a1 1 0 1 0 0 2h6a1 1 0 1 0 0-2H7Z" />
                </svg>
              </span>
              관리자 패널
            </button>
          )}

          <div className="user-menu-divider" />

          <button
            className="user-menu-item user-menu-item-danger"
            role="menuitem"
            onClick={() => { setOpen(false); onLogout(); }}
          >
            <span className="user-menu-icon" aria-hidden>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M10 17l-1.4-1.4 2.6-2.6H3v-2h8.2l-2.6-2.6L10 7l5 5-5 5Zm-5-15h12a2 2 0 0 1 2 2v4h-2V4H5v16h12v-4h2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z" />
              </svg>
            </span>
            로그아웃
          </button>
        </div>
      )}
    </div>
  );
}
