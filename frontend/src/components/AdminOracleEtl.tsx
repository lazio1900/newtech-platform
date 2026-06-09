/**
 * Oracle→PG ETL 관리 — 운영 현장 튜닝을 UI로.
 * 연결은 'DB 연결' 탭의 Oracle 연결을 사용. 여기선 테이블/컬럼 매핑 수정 + probe + 동기화 실행.
 */
import { Fragment, useEffect, useState } from 'react';
import './AdminOracleEtl.css';
import {
  adminOracleEtlApi,
  type EtlRunResult,
  type OracleMapping,
  type OracleProbe,
} from '../api/adminOracleEtl';

export default function AdminOracleEtl() {
  const [mappings, setMappings] = useState<OracleMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<EtlRunResult | null>(null);
  const [probe, setProbe] = useState<OracleProbe | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      setMappings(await adminOracleEtlApi.mappings());
    } catch (e) {
      setErr(apiErr(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const patch = (it: string, p: Partial<OracleMapping>) =>
    setMappings((ms) => ms.map((m) => (m.internal_table === it ? { ...m, ...p } : m)));

  const save = async (m: OracleMapping) => {
    setBusy(m.internal_table);
    setErr(null);
    try {
      await adminOracleEtlApi.updateMapping(m.internal_table, {
        oracle_table: m.oracle_table,
        column_overrides: m.column_overrides,
        enabled: m.enabled,
      });
      await load();
    } catch (e) {
      setErr(apiErr(e));
    } finally {
      setBusy(null);
    }
  };

  const doProbe = async () => {
    setBusy('probe');
    setErr(null);
    try {
      setProbe(await adminOracleEtlApi.probe());
    } catch (e) {
      setErr(apiErr(e));
    } finally {
      setBusy(null);
    }
  };

  const doRun = async () => {
    setBusy('run');
    setErr(null);
    setRunResult(null);
    try {
      setRunResult(await adminOracleEtlApi.run());
    } catch (e) {
      setErr(apiErr(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="admin-oracle-etl">
      <h3>Oracle → PG 동기화 (내부형식 미러)</h3>
      <p className="oetl-desc">
        정보계 Oracle 의 <code>CCTR_*</code>/<code>CUWT_NIC_RLES_*</code> 를 PG 내부형식으로 미러합니다.
        연결은 <strong>‘DB 연결’ 탭의 Oracle 연결</strong>을 사용합니다. 사내 실제 테이블/컬럼명이 다르면
        아래 매핑만 수정하세요(코드 변경 불필요).
      </p>

      <div className="oetl-actions">
        <button type="button" onClick={doProbe} disabled={!!busy}>
          {busy === 'probe' ? '조회 중…' : 'Oracle 스키마 조회(probe)'}
        </button>
        <button type="button" onClick={doRun} disabled={!!busy} className="oetl-run">
          {busy === 'run' ? '동기화 중…' : '동기화 실행 (Oracle → PG)'}
        </button>
      </div>

      {err && <div className="oetl-err">⚠ {err}</div>}

      {runResult && (
        <div className="oetl-result">
          <strong>동기화 완료</strong> · {runResult.source} · 총 {runResult.total_rows.toLocaleString()}행
          <table className="oetl-table">
            <thead><tr><th>Oracle</th><th>→ PG</th><th>상태</th><th>행</th></tr></thead>
            <tbody>
              {runResult.tables.map((t) => (
                <tr key={t.pg_table} className={t.status === 'error' ? 'oetl-row-err' : ''}>
                  <td>{t.oracle_table}</td><td>{t.pg_table}</td>
                  <td>{t.status}{t.error ? `: ${t.error}` : ''}</td>
                  <td>{t.rows ?? '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {probe && (
        <div className="oetl-probe">
          <strong>Oracle 실제 테이블 {probe.tables.length}개</strong> (매핑 입력 참고)
          <div className="oetl-probe-list">{probe.tables.join(', ') || '(없음)'}</div>
        </div>
      )}

      <h4>테이블 매핑 ({mappings.length})</h4>
      {loading ? <div>불러오는 중…</div> : (
        <table className="oetl-table">
          <thead>
            <tr><th>내부형식(PG)</th><th>Oracle 물리 테이블명</th><th>사용</th><th>컬럼</th><th></th></tr>
          </thead>
          <tbody>
            {mappings.map((m) => {
              const ovCount = Object.keys(m.column_overrides || {}).length;
              return (
                <Fragment key={m.internal_table}>
                  <tr>
                    <td><code>{m.internal_table}</code></td>
                    <td>
                      <input value={m.oracle_table}
                             onChange={(e) => patch(m.internal_table, { oracle_table: e.target.value })}
                             className={m.oracle_table !== m.default_oracle_table ? 'oetl-changed' : ''} />
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <input type="checkbox" checked={m.enabled}
                             onChange={(e) => patch(m.internal_table, { enabled: e.target.checked })} />
                    </td>
                    <td>
                      <button type="button" className="oetl-link"
                              onClick={() => setExpanded(expanded === m.internal_table ? null : m.internal_table)}>
                        {m.columns.length}개{ovCount ? ` · 오버라이드 ${ovCount}` : ''}
                      </button>
                    </td>
                    <td>
                      <button type="button" onClick={() => save(m)} disabled={busy === m.internal_table}>
                        {busy === m.internal_table ? '저장 중…' : '저장'}
                      </button>
                    </td>
                  </tr>
                  {expanded === m.internal_table && (
                    <tr><td colSpan={5}>
                      <ColumnOverrides m={m} onChange={(co) => patch(m.internal_table, { column_overrides: co })} />
                    </td></tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function ColumnOverrides({ m, onChange }: { m: OracleMapping; onChange: (co: Record<string, string>) => void }) {
  return (
    <div className="oetl-cols">
      <div className="oetl-cols-hint">PG 컬럼 → Oracle 컬럼. 다른 것만 우측 입력(비우면 PG명 대문자 기본).</div>
      {m.columns.map((c) => (
        <div key={c.pg} className="oetl-col-row">
          <code>{c.pg}</code>
          <span>→</span>
          <input
            defaultValue={m.column_overrides[c.pg] || ''}
            placeholder={c.pg.toUpperCase()}
            onBlur={(e) => {
              const co = { ...m.column_overrides };
              const v = e.target.value.trim();
              if (v) co[c.pg] = v; else delete co[c.pg];
              onChange(co);
            }}
          />
        </div>
      ))}
    </div>
  );
}

function apiErr(e: unknown): string {
  const x = e as { response?: { data?: { detail?: string } }; message?: string };
  return x?.response?.data?.detail || x?.message || '요청 실패';
}
