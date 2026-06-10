import { useState } from 'react';
import { login } from '../api/auth';
import './LoginPage.css';

interface LoginPageProps {
  onLogin: (user: import('../types/loan').User) => void;
  onGoRegister: () => void;
}

export default function LoginPage({ onLogin, onGoRegister }: LoginPageProps) {
  const [userId, setUserId] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);

  const handleLogin = async () => {
    if (!userId || !password) {
      setError('아이디와 비밀번호를 입력해주세요.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const data = await login(userId, password);

      if (data.status === 'success' && data.user) {
        onLogin(data.user);
      } else {
        setError(data.message || '로그인에 실패했습니다.');
      }
    } catch {
      setError('서버에 연결할 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleLogin();
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-header">
          <img src="/capital_CI.png" alt="JB우리캐피탈" className="login-logo" />
          <p>질권 담보 대출 업무 플랫폼</p>
        </div>

        <div className="login-form">
          <div className="login-field">
            <label>아이디</label>
            <input
              type="text"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="아이디를 입력하세요"
              disabled={loading}
            />
          </div>

          <div className="login-field">
            <label>비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="비밀번호를 입력하세요"
              disabled={loading}
            />
          </div>

          {error && <p className="login-error">{error}</p>}

          <button
            className="login-btn"
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? '로그인 중...' : '로그인'}
          </button>

          <div className="login-footer">
            <span>계정이 없으신가요?</span>
            <button className="register-link" onClick={onGoRegister}>
              회원가입
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
