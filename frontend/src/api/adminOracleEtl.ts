/**
 * Oracle→PG ETL 관리 API 클라이언트. /api/admin/oracle-etl/*
 */
import apiClient from './client';

export interface OracleColMap {
  pg: string;
  oracle: string;
}

export interface OracleMapping {
  internal_table: string;
  oracle_table: string;
  default_oracle_table: string;
  columns: OracleColMap[];
  column_overrides: Record<string, string>;
  enabled: boolean;
}

export interface EtlRunTable {
  pg_table: string;
  oracle_table: string;
  status: string;
  rows?: number;
  error?: string;
}

export interface EtlRunResult {
  source: string;
  total_rows: number;
  tables: EtlRunTable[];
}

export interface OracleProbe {
  source: string;
  tables: string[];
  columns: Record<string, string[]>;
}

export const adminOracleEtlApi = {
  mappings: async (): Promise<OracleMapping[]> => {
    const { data } = await apiClient.get<{ mappings: OracleMapping[] }>('/api/admin/oracle-etl/mappings');
    return data.mappings;
  },
  updateMapping: async (
    internalTable: string,
    body: { oracle_table?: string; column_overrides?: Record<string, string>; enabled?: boolean },
  ): Promise<void> => {
    await apiClient.put(`/api/admin/oracle-etl/mappings/${encodeURIComponent(internalTable)}`, body);
  },
  probe: async (): Promise<OracleProbe> => {
    const { data } = await apiClient.get<OracleProbe>('/api/admin/oracle-etl/probe', { timeout: 30_000 });
    return data;
  },
  run: async (): Promise<EtlRunResult> => {
    const { data } = await apiClient.post<EtlRunResult>('/api/admin/oracle-etl/run', {}, { timeout: 180_000 });
    return data;
  },
};
