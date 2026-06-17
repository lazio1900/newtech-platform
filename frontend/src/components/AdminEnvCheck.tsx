import { useCallback, useEffect, useState } from 'react';
import {
  adminEnvCheckApi,
  type EnvCheckResponse,
  type OidcConfig,
  type TokenVerifyResponse,
} from '../api/adminEnvCheck';
import './AdminEnvCheck.css';

interface Props {
  /** 미충족 항목의 deep-link 클릭 시 관리자 패널의 다른 서브탭으로 이동 */
  onNavigate?: (subTab: 'db' | 'llm' | 'users') => void;
}

const SOURCE_LABEL: Record<OidcConfig['source'], string> = {
  db: '화면 저장값',
  env: '.env',
  default: '기본',
};

export default function AdminEnvCheck({ onNavigate }: Props) {
  const [data, setData] = useState<EnvCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [token, setToken] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<TokenVerifyResponse | null>(null);

  const [oidcSource, setOidcSource] = useState<OidcConfig['source'] | null>(null);
  const [oidcForm, setOidcForm] = useState({
    issuer: '', realm: '', client_id: '', jwks_url: '', employee_claim: '', roles_claim: '',
  });
  const [oidcSaving, setOidcSaving] = useState(false);
  const [oidcError, setOidcError] = useState<string | null>(null);
  const [oidcSuccess, setOidcSuccess] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const r = await adminEnvCheckApi.getEnvCheck();
      setData(r);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e?.response?.data?.detail || e?.message || '환경 점검 조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadOidcConfig = useCallback(async () => {
    try {
      const cfg = await adminEnvCheckApi.getConfig();
      setOidcSource(cfg.source);
      setOidcForm({
        issuer: cfg.issuer,
        realm: cfg.realm,
        client_id: cfg.client_id,
        jwks_url: cfg.jwks_url,
        employee_claim: cfg.employee_claim,
        roles_claim: cfg.roles_claim,
      });
    } catch {
      // 설정 조회 실패는 폼을 빈 상태로 두고 조용히 무시
    }
  }, []);

  useEffect(() => { load(); loadOidcConfig(); }, [load, loadOidcConfig]);

  const handleLink = (link: string | null) => {
    if (!link || !onNavigate) return;
    if (link.includes('db-connections')) onNavigate('db');
    else if (link.includes('llm')) onNavigate('llm');
    else if (link.includes('users')) onNavigate('users');
  };

  const handleVerify = async () => {
    const t = token.trim();
    if (!t) return;
    setVerifying(true); setVerifyError(null); setVerifyResult(null);
    try {
      const r = await adminEnvCheckApi.verifyToken(t);
      setVerifyResult(r);
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setVerifyError(e?.response?.data?.detail || e?.message || '토큰 검증 실패');
    } finally {
      setVerifying(false);
    }
  };

  const handleOidcSave = async () => {
    setOidcSaving(true); setOidcError(null); setOidcSuccess(false);
    try {
      const res = await adminEnvCheckApi.saveConfig(oidcForm);
      setOidcSource(res.config.source);
      setOidcSuccess(true);
      load();
    } catch (err) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setOidcError(e?.response?.data?.detail || e?.message || '설정 저장 실패');
    } finally {
      setOidcSaving(false);
    }
  };

  const handleOidcField = (field: keyof typeof oidcForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setOidcForm((prev) => ({ ...prev, [field]: e.target.value }));

  return (
    <div className="admin-env-check">
      <div className="aec-titlebar">
        <div className="aec-titlebar-left">
          <h2 className="aec-title">환경 연동 점검</h2>
          {data && <span className="aec-env-badge">{data.environment}</span>}
        </div>
        <button type="button" className="aec-btn-secondary" onClick={load} disabled={loading}>
          {loading ? '확인 중…' : '새로고침'}
        </button>
      </div>

      <p className="aec-desc">
        현재 환경의 연동 상태를 자동 점검합니다. 미충족 항목은 옆의 링크로 이동해 해결하세요.
      </p>

      {error && <div className="aec-alert aec-alert-error">{error}</div>}

      {data && (
        <div className={`aec-summary ${data.all_ok ? 'ok' : 'warn'}`}>
          {data.all_ok ? '✓ 모든 연동 정상' : '⚠ 일부 연동 미충족 — 아래 항목을 확인하세요'}
        </div>
      )}

      {data && data.config.length > 0 && (
        <section className="aec-section">
          <h3 className="aec-section-title">환경 설정</h3>
          <table className="aec-config-table">
            <tbody>
              {data.config.map((row) => (
                <tr key={row.label}>
                  <th>{row.label}</th>
                  <td>{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {data && data.items.length > 0 && (
        <section className="aec-section">
          <h3 className="aec-section-title">연동 점검</h3>
          <div className="aec-items">
            {data.items.map((it) => (
              <div key={it.key} className="aec-item">
                <span className={`aec-status-dot ${it.ok ? 'ok' : 'fail'}`}>
                  {it.ok ? '✓' : '✕'}
                </span>
                <div className="aec-item-body">
                  <div className="aec-item-label">{it.label}</div>
                  <div className="aec-item-detail">{it.detail}</div>
                </div>
                {it.link && !it.ok && (
                  <button type="button" className="aec-btn-primary" onClick={() => handleLink(it.link)}>
                    바로가기
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="aec-section">
        <div className="aec-oidc-header">
          <h3 className="aec-section-title" style={{ margin: 0 }}>Keycloak / OIDC 설정</h3>
          {oidcSource && (
            <span className={`aec-source-badge aec-source-${oidcSource}`}>
              {SOURCE_LABEL[oidcSource]}
            </span>
          )}
        </div>
        <p className="aec-desc">
          DB에 저장한 값이 .env 설정보다 우선 적용됩니다. 비워두면 .env 또는 기본값을 사용합니다.
        </p>
        <div className="aec-oidc-form">
          <div className="aec-oidc-row">
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">Issuer URL</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.issuer}
                onChange={handleOidcField('issuer')}
                placeholder="https://keycloak.example.com/realms/myrealm"
              />
            </div>
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">Realm</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.realm}
                onChange={handleOidcField('realm')}
                placeholder="myrealm"
              />
            </div>
          </div>
          <div className="aec-oidc-row">
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">Client ID</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.client_id}
                onChange={handleOidcField('client_id')}
                placeholder="my-client"
              />
            </div>
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">JWKS URL</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.jwks_url}
                onChange={handleOidcField('jwks_url')}
                placeholder="비워두면 issuer + /protocol/openid-connect/certs 파생"
              />
            </div>
          </div>
          <div className="aec-oidc-row">
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">사번 클레임 (employee_claim)</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.employee_claim}
                onChange={handleOidcField('employee_claim')}
                placeholder="employee_number"
              />
            </div>
            <div className="aec-oidc-field">
              <label className="aec-oidc-label">역할 클레임 (roles_claim)</label>
              <input
                className="aec-oidc-input"
                value={oidcForm.roles_claim}
                onChange={handleOidcField('roles_claim')}
                placeholder="roles"
              />
            </div>
          </div>
          {oidcError && <div className="aec-alert aec-alert-error">{oidcError}</div>}
          {oidcSuccess && <div className="aec-alert aec-alert-success">설정이 저장되었습니다.</div>}
          <div className="aec-oidc-actions">
            <button
              type="button"
              className="aec-btn-primary"
              onClick={handleOidcSave}
              disabled={oidcSaving}
            >
              {oidcSaving ? '저장 중…' : '저장'}
            </button>
          </div>
        </div>
      </section>

      <section className="aec-section">
        <h3 className="aec-section-title">토큰 검증</h3>
        <p className="aec-desc">SSO/게이트웨이 토큰을 붙여넣어 클레임과 유효성을 확인합니다.</p>
        <textarea
          className="aec-token-input"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder="검증할 토큰을 여기에 붙여넣으세요"
          rows={4}
        />
        <div className="aec-token-actions">
          <button
            type="button"
            className="aec-btn-primary"
            onClick={handleVerify}
            disabled={verifying || !token.trim()}
          >
            {verifying ? '검증 중…' : '검증'}
          </button>
        </div>

        {verifyError && <div className="aec-alert aec-alert-error">{verifyError}</div>}

        {verifyResult && (
          <div className={`aec-verify-result ${verifyResult.verified ? 'ok' : 'warn'}`}>
            <div className="aec-verify-head">
              <span className={`aec-status-dot ${verifyResult.verified ? 'ok' : 'fail'}`}>
                {verifyResult.verified ? '✓' : '✕'}
              </span>
              <span className="aec-verify-detail">{verifyResult.detail}</span>
            </div>

            <table className="aec-config-table">
              <tbody>
                <tr>
                  <th>유효(valid)</th>
                  <td>{verifyResult.valid ? '예' : '아니오'}</td>
                </tr>
                <tr>
                  <th>검증(verified)</th>
                  <td>{verifyResult.verified ? '예' : '아니오'}</td>
                </tr>
                <tr>
                  <th>사번</th>
                  <td>{verifyResult.claims.employee_number ?? '—'}</td>
                </tr>
                <tr>
                  <th>이메일</th>
                  <td>{verifyResult.claims.email ?? '—'}</td>
                </tr>
                <tr>
                  <th>역할</th>
                  <td>{verifyResult.claims.roles.length ? verifyResult.claims.roles.join(', ') : '—'}</td>
                </tr>
              </tbody>
            </table>

            {verifyResult.issues.length > 0 && (
              <ul className="aec-issues">
                {verifyResult.issues.map((iss, i) => (
                  <li key={i}>{iss}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
