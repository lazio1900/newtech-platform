/**
 * 화면 인터페이스 사용자 선호도 — localStorage 기반.
 * 컴포넌트(InterfaceSettings)에서 분리해 Fast Refresh 규칙 준수.
 */

export type FontSize = 'small' | 'medium' | 'large';
export type Density = 'normal' | 'compact';
export type DefaultTab = 'dashboard' | 'direct' | 'applications' | 'monitoring';

export const LS_KEYS = {
  fontSize: 'ui.font_size',
  density: 'ui.density',
  defaultTab: 'ui.default_tab',
} as const;

export const FONT_SIZE_PX: Record<FontSize, number> = { small: 13, medium: 14, large: 16 };
export const ROW_PADDING_PX: Record<Density, number> = { normal: 10, compact: 5 };

export function applyInterfacePrefs(): void {
  const font = (localStorage.getItem(LS_KEYS.fontSize) as FontSize) || 'medium';
  const density = (localStorage.getItem(LS_KEYS.density) as Density) || 'normal';
  const root = document.documentElement;
  root.style.setProperty('--app-font-size', `${FONT_SIZE_PX[font]}px`);
  root.style.setProperty('--app-row-padding', `${ROW_PADDING_PX[density]}px`);
}

export function getDefaultTab(): DefaultTab {
  return (localStorage.getItem(LS_KEYS.defaultTab) as DefaultTab) || 'dashboard';
}
