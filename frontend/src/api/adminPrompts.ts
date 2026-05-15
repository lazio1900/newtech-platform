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
  content: string | null;         // DB override content (has_override=true 일 때만)
  default_content: string | null; // 코드 default
  updated_at: string | null;
  updated_by: string | null;
}

export const adminPromptsApi = {
  list: async (): Promise<PromptItem[]> => {
    const { data } = await apiClient.get<{ status: string; items: PromptItem[] }>(
      '/api/admin/llm/prompts',
    );
    return data.items;
  },

  upsert: async (feature_key: string, prompt_key: string, content: string): Promise<void> => {
    await apiClient.post('/api/admin/llm/prompts', { feature_key, prompt_key, content });
  },

  reset: async (feature_key: string, prompt_key: string): Promise<void> => {
    await apiClient.delete(`/api/admin/llm/prompts/${feature_key}/${prompt_key}`);
  },
};
