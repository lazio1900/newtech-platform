/**
 * 화면 인터페이스 설정 — 글자 크기, 표 밀도, 기본 진입 탭.
 * localStorage 값은 lib/interfacePrefs.ts 에서 관리.
 */
import { useEffect, useState } from 'react';
import {
  LS_KEYS, FONT_SIZE_PX, ROW_PADDING_PX, getDefaultTab,
  type FontSize, type Density, type DefaultTab,
} from '../lib/interfacePrefs';
import './InterfaceSettings.css';

export default function InterfaceSettings() {
  const [fontSize, setFontSize] = useState<FontSize>(
    (localStorage.getItem(LS_KEYS.fontSize) as FontSize) || 'medium',
  );
  const [density, setDensity] = useState<Density>(
    (localStorage.getItem(LS_KEYS.density) as Density) || 'normal',
  );
  const [defaultTab, setDefaultTabState] = useState<DefaultTab>(getDefaultTab());
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  // 변경 시 즉시 미리보기 (저장 안 해도 화면 반영)
  useEffect(() => {
    document.documentElement.style.setProperty('--app-font-size', `${FONT_SIZE_PX[fontSize]}px`);
  }, [fontSize]);
  useEffect(() => {
    document.documentElement.style.setProperty('--app-row-padding', `${ROW_PADDING_PX[density]}px`);
  }, [density]);

  const handleSave = () => {
    localStorage.setItem(LS_KEYS.fontSize, fontSize);
    localStorage.setItem(LS_KEYS.density, density);
    localStorage.setItem(LS_KEYS.defaultTab, defaultTab);
    setSavedMsg('저장되었습니다.');
    setTimeout(() => setSavedMsg(null), 2000);
  };

  return (
    <div className="interface-settings">
      <section className="is-card">
        <header className="is-card-header">
          <h3>표시 설정</h3>
          <p>글자 크기와 표 밀도는 변경 즉시 화면에 반영됩니다.</p>
        </header>

        <div className="is-row">
          <div className="is-row-label">
            글자 크기
            <small>본문 텍스트 크기</small>
          </div>
          <div className="is-row-control">
            <select
              className="is-select"
              value={fontSize}
              onChange={(e) => setFontSize(e.target.value as FontSize)}
            >
              <option value="small">작게 (13px)</option>
              <option value="medium">보통 (14px)</option>
              <option value="large">크게 (16px)</option>
            </select>
          </div>
        </div>

        <div className="is-row">
          <div className="is-row-label">
            표 밀도
            <small>표·목록 행 간격</small>
          </div>
          <div className="is-row-control">
            <select
              className="is-select"
              value={density}
              onChange={(e) => setDensity(e.target.value as Density)}
            >
              <option value="normal">보통</option>
              <option value="compact">컴팩트</option>
            </select>
          </div>
        </div>
      </section>

      <section className="is-card">
        <header className="is-card-header">
          <h3>탐색 설정</h3>
          <p>로그인 시 처음 보여줄 화면을 선택합니다.</p>
        </header>

        <div className="is-row">
          <div className="is-row-label">
            기본 진입 탭
            <small>다음 로그인부터 적용</small>
          </div>
          <div className="is-row-control">
            <select
              className="is-select"
              value={defaultTab}
              onChange={(e) => setDefaultTabState(e.target.value as DefaultTab)}
            >
              <option value="dashboard">대시보드</option>
              <option value="direct">직접조회하기</option>
              <option value="applications">대부업체 신청건</option>
              <option value="monitoring">사후모니터링</option>
            </select>
          </div>
        </div>

        <footer className="is-card-footer">
          {savedMsg && <span className="is-msg ok">{savedMsg}</span>}
          <button className="is-btn-primary" onClick={handleSave}>설정 저장</button>
        </footer>
      </section>
    </div>
  );
}
