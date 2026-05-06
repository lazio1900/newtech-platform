import { useEffect, useState } from 'react';
import './App.css';
import { getMe, logout as apiLogout } from './api/auth';
import { getToken } from './api/session';
import LoginPage from './components/LoginPage';
import RegisterPage from './components/RegisterPage';
import CustomerDashboard from './components/CustomerDashboard';
import AuditorDashboard from './components/AuditorDashboard';
import { User } from '@/types/loan';

type Page = 'login' | 'register';

function App() {
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [page, setPage] = useState<Page>('login');
  const [restoring, setRestoring] = useState<boolean>(true);

  // 시작 시 토큰이 있으면 /api/me로 세션 복원
  useEffect(() => {
    const token = getToken();
    if (!token) {
      setRestoring(false);
      return;
    }
    let cancelled = false;
    getMe()
      .then((res) => {
        if (cancelled) return;
        if (res.status === 'success' && res.user) {
          setCurrentUser(res.user);
        }
      })
      .catch(() => {
        // 401은 client interceptor가 처리. 이 경우 사용자 미설정.
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogin = (user: User) => {
    setCurrentUser(user);
  };

  const handleLogout = () => {
    apiLogout();
    setCurrentUser(null);
    setPage('login');
  };

  if (restoring) {
    return <div className="app-loading">로그인 정보 확인 중…</div>;
  }

  if (!currentUser) {
    if (page === 'register') {
      return <RegisterPage onBack={() => setPage('login')} />;
    }
    return (
      <LoginPage
        onLogin={handleLogin}
        onGoRegister={() => setPage('register')}
      />
    );
  }

  if (currentUser.role === 'customer') {
    return <CustomerDashboard user={currentUser} onLogout={handleLogout} />;
  }

  return <AuditorDashboard user={currentUser} onLogout={handleLogout} />;
}

export default App;
