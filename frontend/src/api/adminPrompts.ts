/**
 * 관리자용 LLM 프롬프트 편집 API 클라이언트.
 * Backend: /api/admin/llm/prompts/*
 */
import apiClient from './client';

export interface PromptItem {
  feature_key: string;
  feature_label: string;
  feature_description: string;
  prompt_key: string;
  prompt_label: string;
  prompt_description: string;
  has_override: boolean;
  version: number | null;
  content: string | null;
  default_content: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PromptVersion {
  id: number;
  feature_key: string;
  prompt_key: string;
  version: number;
  is_active: boolean;
  content: string;
  created_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface PromptSample {
  label: string;
  user_input: string;
  json_mode?: boolean;
}

export interface PromptTestResult {
  elapsed_ms: number;
  model: string | null;
  text: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  finish_reason: string | null;
}

export const adminPromptsApi = {
  list: async (): Promise<PromptItem[]> => {
    const { data } = await apiClient.get<{ status: string; items: PromptItem[] }>(
      '/api/admin/llm/prompts',
    );
    return data.items;
  },

  versions: async (feature_key: string, prompt_key: string): Promise<PromptVersion[]> => {
    const { data } = await apiClient.get<{ status: string; versions: PromptVersion[] }>(
      `/api/admin/llm/prompts/${feature_key}/${prompt_key}/versions`,
    );
    return data.versions;
  },

  /** 해당 프롬프트에 미리 정의된 테스트 샘플 목록. */
  samples: async (feature_key: string, prompt_key: string): Promise<PromptSample[]> => {
    const { data } = await apiClient.get<{ status: string; samples: PromptSample[] }>(
      `/api/admin/llm/prompts/${feature_key}/${prompt_key}/samples`,
    );
    return data.samples;
  },

  /** 새 버전으로 저장. 이전 활성 버전은 자동 비활성화. */
  upsert: async (feature_key: string, prompt_key: string, content: string): Promise<void> => {
    await apiClient.post('/api/admin/llm/prompts', { feature_key, prompt_key, content });
  },

  /** 과거 버전 활성화 (롤백). */
  activate: async (feature_key: string, prompt_key: string, version: number): Promise<void> => {
    await apiClient.post(`/api/admin/llm/prompts/${feature_key}/${prompt_key}/activate/${version}`);
  },

  /** adhoc 테스트 — 저장 없이 LLM 1회 호출. */
  test: async (content: string, user_input: string, json_mode = false): Promise<PromptTestResult> => {
    const { data } = await apiClient.post<{ status: string } & PromptTestResult>(
      '/api/admin/llm/prompts/test',
      { content, user_input, json_mode },
      { timeout: 120_000 },
    );
    return data;
  },

  reset: async (feature_key: string, prompt_key: string): Promise<void> => {
    await apiClient.delete(`/api/admin/llm/prompts/${feature_key}/${prompt_key}`);
  },
};
