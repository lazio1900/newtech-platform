# `_to_extract/` — 추출 예정 코드

본 디렉토리의 코드는 **데이터 수집(crawling/collection) 도메인**에 속하며,
별도 레포로 추출될 예정이다. ADR-001, ADR-003 참조.

## 포함된 모듈

- `connectors/` — KB부동산, 국토부 API 커넥터
- `browser/` — Playwright 세션 관리 (KB API 폴백용)
- `workers/` — Celery 태스크 (수집 작업 큐)
- `services/sync_collector.py` — 동기 수집 로직
- `services/complex_discovery.py` — 단지 발견 서비스
- `routers/jobs.py`, `runs.py`, `batches.py`, `data_explorer.py` — 수집 작업 관리/조회 API
- `seed_*.py` — 초기 시드 스크립트

## 본 앱에서의 영향

- `backend/main.py`에서 위 라우터 로드 제거됨
- `backend/routers/complexes.py`의 일부 엔드포인트 (POST/discovery 트리거)는
  `_to_extract` 모듈을 inline import하므로 호출 시 ImportError 발생 → Phase 1에서
  해당 엔드포인트들을 surgically 제거할 예정. GET 엔드포인트(read-only)는 정상 동작.
- `requirements.txt`에서 `playwright`, `celery` 의존성 제거 (수집기 레포로 이전)

## 추출 시 절차 (향후)

1. 별도 레포 (예: `newtech-collector`) 생성
2. 본 디렉토리 내용 이전
3. ORM 모델은 본 앱과 공유하기 위해 패키지화 (`newtech-models`) 또는 코드 사본 유지
4. 수집기는 PostgreSQL에 직접 쓰기 (ADR-002의 동일 DB 공유)
5. 본 디렉토리 삭제
