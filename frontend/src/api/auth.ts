import apiClient from './client';
import { clearToken, setToken } from './session';
import type { User } from '@/types/loan';

interface LoginResponse {
  status: 'success' | 'error';
  access_token?: string;
  token_type?: string;
  expires_in_minutes?: number;
  user?: User;
  message?: string;
}

interface RegisterResponse {
  status: 'success' | 'error';
  message?: string;
}

interface MeResponse {
  status: 'success' | 'error';
  user?: User;
}

export const login = async (userId: string, password: string): Promise<LoginResponse> => {
  const { data } = await apiClient.post<LoginResponse>('/api/login', {
    user_id: userId,
    password,
  });
  if (data.status === 'success' && data.access_token) {
    setToken(data.access_token);
  }
  return data;
};

export const register = async (userData: {
  user_id: string;
  password: string;
  company_name: string;
  ceo_name: string;
  business_number: string;
  phone: string;
}): Promise<RegisterResponse> => {
  const { data } = await apiClient.post<RegisterResponse>('/api/register', userData);
  return data;
};

export const getMe = async (): Promise<MeResponse> => {
  const { data } = await apiClient.get<MeResponse>('/api/me');
  return data;
};

export const logout = (): void => {
  clearToken();
};
