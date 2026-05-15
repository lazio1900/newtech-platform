/**
 * 사용자 본인 셀프 서비스 + 관리자용 사용자 CRUD API 클라이언트.
 *
 * - 본인: PATCH /api/me, POST /api/me/password
 * - 관리자: /api/admin/users/* (목록·생성·수정·비번 reset·삭제)
 */
import apiClient from './client';

// ----- 본인 셀프 서비스 -----

export interface MeUpdatePayload {
  company_name?: string | null;
  ceo_name?: string | null;
  business_number?: string | null;
  phone?: string | null;
}

export const accountApi = {
  updateProfile: async (payload: MeUpdatePayload): Promise<void> => {
    await apiClient.patch('/api/me', payload);
  },

  changePassword: async (currentPassword: string, newPassword: string): Promise<void> => {
    await apiClient.post('/api/me/password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },
};


// ----- 관리자용 -----

export type UserRole = 'customer' | 'auditor' | 'admin';

export interface AdminUser {
  user_id: string;
  role: UserRole;
  company_name: string | null;
  ceo_name: string | null;
  business_number: string | null;
  phone: string | null;
  is_active: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export interface AdminUserCreatePayload {
  user_id: string;
  password: string;
  role: UserRole;
  company_name?: string | null;
  ceo_name?: string | null;
  business_number?: string | null;
  phone?: string | null;
}

export interface AdminUserUpdatePayload {
  role?: UserRole | null;
  is_active?: boolean | null;
  company_name?: string | null;
  ceo_name?: string | null;
  business_number?: string | null;
  phone?: string | null;
}

export interface AdminUserListResponse {
  status: string;
  total: number;
  page: number;
  page_size: number;
  items: AdminUser[];
}

export const adminUsersApi = {
  list: async (params: {
    search?: string;
    role?: UserRole;
    is_active?: boolean;
    page?: number;
    page_size?: number;
  } = {}): Promise<AdminUserListResponse> => {
    const { data } = await apiClient.get<AdminUserListResponse>('/api/admin/users', { params });
    return data;
  },

  create: async (payload: AdminUserCreatePayload): Promise<AdminUser> => {
    const { data } = await apiClient.post<{ status: string; user: AdminUser }>(
      '/api/admin/users', payload,
    );
    return data.user;
  },

  update: async (userId: string, payload: AdminUserUpdatePayload): Promise<AdminUser> => {
    const { data } = await apiClient.patch<{ status: string; user: AdminUser }>(
      `/api/admin/users/${encodeURIComponent(userId)}`, payload,
    );
    return data.user;
  },

  resetPassword: async (userId: string, newPassword: string): Promise<void> => {
    await apiClient.post(
      `/api/admin/users/${encodeURIComponent(userId)}/password-reset`,
      { new_password: newPassword },
    );
  },

  deactivate: async (userId: string): Promise<void> => {
    await apiClient.delete(`/api/admin/users/${encodeURIComponent(userId)}`);
  },
};
