import axios from 'axios';
import { clearToken, getToken } from './session';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '';

const apiClient = axios.create({
  baseURL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token && config.headers) {
    config.headers.set('Authorization', `Bearer ${token}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken();
      // 로그인 페이지로 강제 이동. App 트리는 토큰 부재를 감지하면 자동으로 LoginPage 렌더.
      if (typeof window !== 'undefined' && window.location.pathname !== '/') {
        window.location.assign('/');
      }
    } else {
      console.error(`API Error: ${error.response?.data?.detail || error.message}`);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
