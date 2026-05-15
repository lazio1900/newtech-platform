/**
 * 관리자용 DB 연결 API 클라이언트. /api/admin/db/connections/*
 */
import apiClient from './client';

export interface DbConnection {
  id: number;
  name: string;
  driver: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password_masked: string | null;
  has_password: boolean;
  is_active: boolean;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DbConnectionCreatePayload {
  name: string;
  driver?: string;
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string | null;
  is_active?: boolean;
  set_default?: boolean;
}

export interface DbConnectionUpdatePayload {
  name?: string;
  driver?: string;
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string | null;  // 빈 문자열은 미변경
  is_active?: boolean;
}

export interface DbTestResult {
  ok: boolean;
  latency_ms?: number;
  error?: string;
}

export const adminDbApi = {
  list: async (): Promise<DbConnection[]> => {
    const { data } = await apiClient.get<{ status: string; items: DbConnection[] }>(
      '/api/admin/db/connections',
    );
    return data.items;
  },

  create: async (payload: DbConnectionCreatePayload): Promise<DbConnection> => {
    const { data } = await apiClient.post<{ status: string; connection: DbConnection }>(
      '/api/admin/db/connections', payload,
    );
    return data.connection;
  },

  update: async (id: number, payload: DbConnectionUpdatePayload): Promise<DbConnection> => {
    const { data } = await apiClient.patch<{ status: string; connection: DbConnection }>(
      `/api/admin/db/connections/${id}`, payload,
    );
    return data.connection;
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/admin/db/connections/${id}`);
  },

  setDefault: async (id: number): Promise<DbConnection> => {
    const { data } = await apiClient.post<{ status: string; connection: DbConnection }>(
      `/api/admin/db/connections/${id}/set-default`,
    );
    return data.connection;
  },

  test: async (id: number): Promise<DbTestResult> => {
    const { data } = await apiClient.post<{ status: string } & DbTestResult>(
      `/api/admin/db/connections/${id}/test`,
      undefined,
      { timeout: 20_000 },
    );
    return data;
  },
};
