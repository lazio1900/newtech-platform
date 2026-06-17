/**
 * 환경 연동 점검 API 클라이언트.
 */
import apiClient from './client';

export interface OidcConfig {
  issuer: string;
  realm: string;
  client_id: string;
  jwks_url: string;
  employee_claim: string;
  roles_claim: string;
  source: 'db' | 'env' | 'default';
}

export interface EnvCheckItem {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  link: string | null;
}

export interface ConfigRow {
  label: string;
  value: string;
}

export interface EnvCheckResponse {
  status: string;
  environment: string;
  config: ConfigRow[];
  items: EnvCheckItem[];
  all_ok: boolean;
}

export interface TokenVerifyResponse {
  valid: boolean;
  verified: boolean;
  claims: {
    employee_number: string | null;
    email: string | null;
    roles: string[];
  };
  issues: string[];
  detail: string;
}

export const adminEnvCheckApi = {
  getEnvCheck: async (): Promise<EnvCheckResponse> => {
    const { data } = await apiClient.get<EnvCheckResponse>(
      '/api/admin/env-check',
      { timeout: 30_000 },
    );
    return data;
  },
  verifyToken: async (token: string): Promise<TokenVerifyResponse> => {
    const { data } = await apiClient.post<TokenVerifyResponse>(
      '/api/admin/env-check/verify-token',
      { token },
      { timeout: 30_000 },
    );
    return data;
  },
  getConfig: async (): Promise<OidcConfig> => {
    const { data } = await apiClient.get<OidcConfig>(
      '/api/admin/env-check/config',
      { timeout: 15_000 },
    );
    return data;
  },
  saveConfig: async (cfg: Partial<OidcConfig>): Promise<{ status: string; config: OidcConfig }> => {
    const { data } = await apiClient.put<{ status: string; config: OidcConfig }>(
      '/api/admin/env-check/config',
      cfg,
      { timeout: 15_000 },
    );
    return data;
  },
};
