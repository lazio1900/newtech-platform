/**
 * 관리자용 LLM 연결 API 클라이언트.
 * Backend: /api/admin/llm/connections/*
 */
import apiClient from './client';

export interface LlmConnection {
  id: number;
  name: string;
  provider: string;
  base_url: string | null;
  api_key_masked: string | null;
  has_api_key: boolean;
  default_model: string;
  is_active: boolean;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface LlmConnectionCreatePayload {
  name: string;
  provider?: string;          // 기본 'openai'
  base_url?: string | null;
  api_key?: string | null;
  default_model: string;
  is_active?: boolean;
  set_default?: boolean;
}

export interface LlmConnectionUpdatePayload {
  name?: string;
  provider?: string;
  base_url?: string | null;
  api_key?: string | null;    // 빈 문자열은 미변경
  default_model?: string;
  is_active?: boolean;
}

export interface LlmTestResult {
  ok: boolean;
  model?: string;
  latency_ms?: number;
  error?: string;
}

export const adminLlmApi = {
  list: async (): Promise<LlmConnection[]> => {
    const { data } = await apiClient.get<{ status: string; items: LlmConnection[] }>(
      '/api/admin/llm/connections',
    );
    return data.items;
  },

  create: async (payload: LlmConnectionCreatePayload): Promise<LlmConnection> => {
    const { data } = await apiClient.post<{ status: string; connection: LlmConnection }>(
      '/api/admin/llm/connections', payload,
    );
    return data.connection;
  },

  update: async (id: number, payload: LlmConnectionUpdatePayload): Promise<LlmConnection> => {
    const { data } = await apiClient.patch<{ status: string; connection: LlmConnection }>(
      `/api/admin/llm/connections/${id}`, payload,
    );
    return data.connection;
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/admin/llm/connections/${id}`);
  },

  setDefault: async (id: number): Promise<LlmConnection> => {
    const { data } = await apiClient.post<{ status: string; connection: LlmConnection }>(
      `/api/admin/llm/connections/${id}/set-default`,
    );
    return data.connection;
  },

  test: async (id: number): Promise<LlmTestResult> => {
    // 테스트는 외부 LLM 호출 1회 발생 → timeout 넉넉히
    const { data } = await apiClient.post<{ status: string } & LlmTestResult>(
      `/api/admin/llm/connections/${id}/test`,
      undefined,
      { timeout: 60_000 },
    );
    return data;
  },
};
