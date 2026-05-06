import apiClient from './client';

export async function fetchSuggestions(field: string, query: string): Promise<string[]> {
  const response = await apiClient.get<string[]>('/api/suggestions', {
    params: { field, query },
  });
  return response.data;
}
