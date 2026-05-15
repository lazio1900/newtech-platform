/**
 * 외부 데이터 매핑 — logical entity 기준으로 외부 DB 컬럼 → 본 앱 표준 필드 매핑 관리.
 *
 * Phase 1: 매핑 룰 등록·편집·저장 (실제 적용은 Phase 2 의 data_source_adapter 가 담당)
 */
import { useCallback, useEffect, useState } from 'react';
import {
  adminDataMappingsApi,
  type DataMapping,
  type EntityMeta,
  type TransformMeta,
  type FieldMappings,
} from '../api/adminDataMappings';
import { adminDbApi, type DbConnection } from '../api/adminDb';
import './AdminDataMappings.css';

type DialogMode = null | 'create' | 'edit';

export default function AdminDataMappings() {
  const [items, setItems] = useState<DataMapping[]>([]);
  const [entities, setEntities] = useState<EntityMeta[]>([]);
  const [transforms, setTransforms] = useState<TransformMeta[]>([]);
  const [dbConnections, setDbConnections] = useState<DbConnection[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [target, setTarget] = useState<DataMapping | null>(null);

  const fetchAll = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [list, reg, dbs] = await Promise.all([
        adminDataMappingsApi.list(),
        adminDataMappingsApi.registry(),
        adminDbApi.list(),
      ]);
      setItems(list);
      setEntities(reg.entities);
      setTransforms(reg.transforms);
      setDbConnections(dbs);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '데이터 로드 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleDelete = async (m: DataMapping) => {
    if (!confirm(`'${m.name}' 매핑을 삭제하시겠습니까?`)) return;
    try {
      await adminDataMappingsApi.remove(m.id);
      fetchAll();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      alert(e?.response?.data?.detail || e?.message || '삭제 실패');
    }
  };

  return (
    <div className="dmap">
      <div className="dmap-header">
        <div>
          <h3>외부 데이터 매핑</h3>
          <p>사내 이관 후 외부 DB 의 컬럼을 본 앱 표준 모델 필드로 매핑합니다. Phase 1: 룰 등록만, 실제 어댑터 적용은 사내 DB 스키마 확정 후.</p>
        </div>
        <button className="dmap-btn-primary"
                onClick={() => { setTarget(null); setDialog('create'); }}
                disabled={entities.length === 0 || dbConnections.length === 0}>
          + 매핑 추가
        </button>
      </div>

      {dbConnections.length === 0 && (
        <div className="dmap-warning">
          ⚠ 먼저 "DB 연결" 탭에서 외부 DB endpoint 를 등록하세요.
        </div>
      )}

      {error && <div className="dmap-error">{error}</div>}

      {loading && items.length === 0 && (
        <div className="dmap-empty">로딩 중...</div>
      )}

      {!loading && items.length === 0 && (
        <div className="dmap-empty">
          등록된 매핑이 없습니다. 위의 "+ 매핑 추가" 로 시작하세요.
        </div>
      )}

      <div className="dmap-list">
        {items.map((m) => {
          const entity = entities.find((e) => e.key === m.logical_entity);
          const dbConn = dbConnections.find((d) => d.id === m.source_db_connection_id);
          const fieldKeys = Object.keys(m.field_mappings);
          return (
            <div key={m.id} className={`dmap-card ${!m.is_active ? 'inactive' : ''}`}>
              <div className="dmap-card-main">
                <div className="dmap-card-head">
                  <span className="dmap-card-name">{m.name}</span>
                  <span className={`dmap-pill ${m.is_active ? 'dmap-pill-active' : 'dmap-pill-inactive'}`}>
                    {m.is_active ? '활성' : '비활성'}
                  </span>
                  <span className="dmap-pill dmap-pill-entity">{entity?.label || m.logical_entity}</span>
                </div>
                <dl className="dmap-card-meta">
                  <div><dt>외부 DB</dt><dd>{dbConn ? `${dbConn.name} (${dbConn.host}/${dbConn.database})` : `(삭제됨) #${m.source_db_connection_id}`}</dd></div>
                  <div><dt>소스 테이블</dt><dd>{m.source_table}</dd></div>
                  <div><dt>매핑 필드</dt><dd>{fieldKeys.length}개 — {fieldKeys.slice(0, 5).join(', ')}{fieldKeys.length > 5 ? ', ...' : ''}</dd></div>
                  {m.updated_at && (
                    <div><dt>수정</dt><dd>{m.updated_at.replace('T', ' ').slice(0, 16)}{m.updated_by ? ` (${m.updated_by})` : ''}</dd></div>
                  )}
                </dl>
              </div>
              <div className="dmap-card-actions">
                <button className="dmap-btn-ghost" onClick={() => { setTarget(m); setDialog('edit'); }}>수정</button>
                <button className="dmap-btn-ghost-danger" onClick={() => handleDelete(m)}>삭제</button>
              </div>
            </div>
          );
        })}
      </div>

      {dialog && entities.length > 0 && (
        <MappingDialog
          mode={dialog}
          target={target}
          entities={entities}
          transforms={transforms}
          dbConnections={dbConnections}
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); fetchAll(); }}
        />
      )}
    </div>
  );
}


function MappingDialog({ mode, target, entities, transforms, dbConnections, onClose, onSaved }: {
  mode: 'create' | 'edit';
  target: DataMapping | null;
  entities: EntityMeta[];
  transforms: TransformMeta[];
  dbConnections: DbConnection[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(target?.name || '');
  const [entityKey, setEntityKey] = useState<string>(target?.logical_entity || entities[0]?.key || '');
  const [dbConnId, setDbConnId] = useState<number>(
    target?.source_db_connection_id || dbConnections[0]?.id || 0,
  );
  const [sourceTable, setSourceTable] = useState(target?.source_table || '');
  const [isActive, setIsActive] = useState(target?.is_active ?? true);
  const [mappings, setMappings] = useState<FieldMappings>(target?.field_mappings || {});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const entity = entities.find((e) => e.key === entityKey);

  const setFieldMapping = (fieldKey: string, sourceField: string, transform?: string) => {
    setMappings((prev) => {
      const next = { ...prev };
      if (!sourceField) {
        delete next[fieldKey];  // 빈 값이면 매핑 제거
      } else {
        next[fieldKey] = { source_field: sourceField, ...(transform && transform !== 'none' ? { transform } : {}) };
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    setSaving(true); setError(null);
    try {
      if (mode === 'create') {
        await adminDataMappingsApi.create({
          name: name.trim(),
          logical_entity: entityKey,
          source_db_connection_id: dbConnId,
          source_table: sourceTable.trim(),
          field_mappings: mappings,
          is_active: isActive,
        });
      } else if (target) {
        await adminDataMappingsApi.update(target.id, {
          name: name.trim(),
          source_table: sourceTable.trim(),
          field_mappings: mappings,
          is_active: isActive,
        });
      }
      onSaved();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '저장 실패');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="dmap-dialog-backdrop" onClick={onClose}>
      <div className="dmap-dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="dmap-dialog-title">{mode === 'create' ? '매핑 추가' : `매핑 수정: ${target?.name}`}</h3>
        <div className="dmap-dialog-body">
          <div className="dmap-form-row">
            <Field label="이름 *">
              <input className="dmap-input" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
            </Field>
            <Field label="활성">
              <label className="dmap-checkbox">
                <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} /> 활성
              </label>
            </Field>
          </div>

          <div className="dmap-form-row">
            <Field label="표준 엔티티 *">
              <select
                className="dmap-input"
                value={entityKey}
                onChange={(e) => { setEntityKey(e.target.value); setMappings({}); }}
                disabled={mode === 'edit'}
              >
                {entities.map((ent) => (
                  <option key={ent.key} value={ent.key}>{ent.label} ({ent.key})</option>
                ))}
              </select>
            </Field>
            <Field label="외부 DB *">
              <select
                className="dmap-input"
                value={dbConnId}
                onChange={(e) => setDbConnId(parseInt(e.target.value, 10))}
                disabled={mode === 'edit'}
              >
                {dbConnections.map((d) => (
                  <option key={d.id} value={d.id}>{d.name} — {d.host}/{d.database}</option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="소스 테이블·뷰명 *" hint="외부 DB 에서 데이터를 조회할 테이블 또는 뷰의 이름">
            <input className="dmap-input" value={sourceTable} onChange={(e) => setSourceTable(e.target.value)} maxLength={200} />
          </Field>

          {entity && (
            <div className="dmap-mappings">
              <h4>필드 매핑</h4>
              <p className="dmap-mappings-desc">{entity.description}</p>
              <table className="dmap-mapping-table">
                <thead>
                  <tr>
                    <th>표준 필드</th>
                    <th>타입</th>
                    <th>외부 컬럼명</th>
                    <th>변환</th>
                    <th>설명</th>
                  </tr>
                </thead>
                <tbody>
                  {entity.fields.map((f) => {
                    const cur = mappings[f.key];
                    return (
                      <tr key={f.key}>
                        <td>
                          <code>{f.key}</code>
                          {f.required && <span className="dmap-req">*</span>}
                        </td>
                        <td className="dmap-type">{f.type}</td>
                        <td>
                          <input
                            className="dmap-input dmap-input-sm"
                            value={cur?.source_field || ''}
                            onChange={(e) => setFieldMapping(f.key, e.target.value, cur?.transform)}
                            placeholder={`source column for ${f.key}`}
                          />
                        </td>
                        <td>
                          <select
                            className="dmap-input dmap-input-sm"
                            value={cur?.transform || 'none'}
                            onChange={(e) => setFieldMapping(f.key, cur?.source_field || '', e.target.value)}
                            disabled={!cur?.source_field}
                          >
                            {transforms.map((t) => (
                              <option key={t.key} value={t.key}>{t.label}</option>
                            ))}
                          </select>
                        </td>
                        <td className="dmap-desc">{f.description}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {error && <div className="dmap-dialog-error">{error}</div>}
        </div>
        <div className="dmap-dialog-footer">
          <button className="dmap-btn-ghost" onClick={onClose} disabled={saving}>취소</button>
          <button
            className="dmap-btn-primary"
            onClick={handleSubmit}
            disabled={saving || !name.trim() || !sourceTable.trim() || !entityKey || !dbConnId}
          >
            {saving ? '저장 중...' : '저장'}
          </button>
        </div>
      </div>
    </div>
  );
}


function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="dmap-field">
      <label className="dmap-field-label">{label}</label>
      {children}
      {hint && <div className="dmap-field-hint">{hint}</div>}
    </div>
  );
}
