# 작업 이력

## 1. PostgreSQL 포트 수정
**문제**: docker-compose가 5433으로 매핑하는데 .env와 config.py가 5432를 사용
**수정 파일**:
- `backend/.env` — `DATABASE_URL` 포트 5432→5433
- `backend/core/config.py` — `database_url` 기본값 포트 5432→5433

## 2. Celery → BackgroundTasks 전환
**문제**: jobs.py가 `workers.tasks`를 import하여 `.delay()` 호출하는데 Celery worker가 미실행
**수정 파일**:
- `backend/routers/jobs.py`
  - `from workers.tasks import ...` 제거
  - `BackgroundTasks` + `collect_complex_sync()` 직접 호출로 변경
  - `_resolve_complex_ids()` 헬퍼 함수 추가
  - 영향 엔드포인트: `create-and-run`, `{job_id}/run`, `run-region`

## 3. 평수(pyeong) 데이터 수정
**문제**: KB API의 실제 키명이 `"공급면적평"`, `"전용면적평"`인데 코드가 `"평"`, `"평형"`으로 검색
**수정 파일**:
- `backend/services/sync_collector.py` — pyeong 키 검색 순서: `["공급면적평", "전용면적평", "평"]`
- `backend/services/complex_discovery.py` — pyeong 키: `["공급면적평", "전용면적평", "pyeong", "평형", "평", "py"]`, area code 키: `["면적일련번호", "areaNo", ...]`
- DB 기존 28개 area 레코드 업데이트 스크립트 실행 완료

## 4. 공급면적(supply_m2) 프론트엔드 표시
**수정 파일**:
- `frontend/src/components/collector/ComplexDetail.tsx`
  - `formatArea()`: `전용 Xm² / 공급 Ym² (Z평)` 형식
  - 테이블 헤더: "전용면적" → "면적 (전용/공급)"
- `frontend/src/components/collector/PriceTab.tsx`
  - 동일한 `formatArea()` 변경
  - 면적 선택 드롭다운에 공급면적 표시
  - CSV 내보내기에 공급면적 컬럼 추가

## 5. 일괄 지역 발견 (Batch Region Discovery)
**목적**: 시/도 선택 후 시군구 전체 선택 → 일괄 발견 (기존: 하나씩 클릭)
**수정 파일**:
- `frontend/src/hooks/useComplexes.ts`
  - `useBatchDiscoverRegion()` 훅 추가
  - `BatchDiscoverProgress` 인터페이스
  - 순차 API 호출 + AbortController 취소 지원
- `frontend/src/components/collector/ComplexList.tsx`
  - `selectedSigungus: Set<string>` 다중 선택
  - 전체 선택 체크박스
  - 실시간 프로그레스 바 + 결과 누적
  - 모달 푸터: 일괄 발견 / 단일 발견 / 취소

## 6. 사이드바 서브메뉴 (데이터 수집 허브)
**목적**: 3개 탭(수집관리/실행이력/데이터탐색)을 "데이터 수집 허브" 하위로 그룹화
**수정 파일**:
- `frontend/src/components/AuditorDashboard.tsx`
  - 3개 `sidebar-btn` → `sidebar-submenu-wrapper` + 플라이아웃
- `frontend/src/components/AuditorDashboard.css`
  - `.sidebar-submenu-wrapper`, `.sidebar-submenu`, `.sidebar-submenu-btn` 등 CSS 추가
  - hover 시 오른쪽 서브메뉴 표시

## 7. GitHub 저장소 생성
- `gh repo create newtech-platform --public`
- Remote `mygithub` = https://github.com/lazio1900/newtech-platform
- `git push -u mygithub main` 완료

## 빌드 상태
- TypeScript 타입 체크 (`npx tsc --noEmit`): **통과**
- Vite 프로덕션 빌드 (`npx vite build`): **통과**
- Node.js 22.11.0 사용 중 (Vite가 22.12+ 권장하지만 동작함)
