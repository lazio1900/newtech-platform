/**
 * 관리자용 외부 데이터 매핑 API 클라이언트.
 * Backend: /api/admin/data-mappings/*
 */
import apiClient from './client';

export interface FieldMappingValue {
  source_field: string;
  transform?: string;  // none / to_int / to_float / ... (entity_registry.TRANSFORM_REGISTRY)
}

export type FieldMappings = Record<string, FieldMappingValue>;

export interface DataMapping {
  id: number;
  name: string;
  logical_entity: string;
  source_db_connection_id: number;
  source_table: string;
  field_mappings: FieldMappings;
  is_active: boolean;
  created_at: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface MappingCreatePayload {
  name: string;
  logical_entity: string;
  source_db_connection_id: number;
  source_table: string;
  field_mappings: FieldMappings;
  is_active?: boolean;
}

export interface MappingUpdatePayload {
  name?: string;
  source_table?: string;
  field_mappings?: FieldMappings;
  is_active?: boolean;
}

export interface StandardField {
  key: string;
  type: 'int' | 'str' | 'float' | 'date' | 'datetime' | 'bool';
  required: boolean;
  description: string;
}

export interface EntityMeta {
  key: string;
  label: string;
  description: string;
  fields: StandardField[];
}

export interface TransformMeta {
  key: string;
  label: string;
  description: string;
}

export interface RegistryResponse {
  status: string;
  entities: EntityMeta[];
  transforms: TransformMeta[];
}

export interface MappingPreviewResponse {
  status: 'success' | 'error';
  sql: string;
  columns?: string[];
  raw_rows?: Array<Record<string, unknown>>;
  transformed?: Array<Record<string, unknown>>;
  error?: string;
}


export const adminDataMappingsApi = {
  registry: async (): Promise<{ entities: EntityMeta[]; transforms: TransformMeta[] }> => {
    const { data } = await apiClient.get<RegistryResponse>('/api/admin/data-mappings/registry');
    return { entities: data.entities, transforms: data.transforms };
  },

  list: async (): Promise<DataMapping[]> => {
    const { data } = await apiClient.get<{ status: string; items: DataMapping[] }>(
      '/api/admin/data-mappings',
    );
    return data.items;
  },

  create: async (payload: MappingCreatePayload): Promise<DataMapping> => {
    const { data } = await apiClient.post<{ status: string; mapping: DataMapping }>(
      '/api/admin/data-mappings', payload,
    );
    return data.mapping;
  },

  update: async (id: number, payload: MappingUpdatePayload): Promise<DataMapping> => {
    const { data } = await apiClient.patch<{ status: string; mapping: DataMapping }>(
      `/api/admin/data-mappings/${id}`, payload,
    );
    return data.mapping;
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/api/admin/data-mappings/${id}`);
  },

  /** 매핑된 외부 테이블 N rows SELECT + transform 적용 결과 미리보기. */
  preview: async (id: number, limit = 5): Promise<MappingPreviewResponse> => {
    const { data } = await apiClient.post<MappingPreviewResponse>(
      `/api/admin/data-mappings/${id}/preview`,
      { limit },
      { timeout: 30_000 },
    );
    return data;
  },
};
