# 아키텍처 결정 기록 (ADR)

본 문서는 newtech-platform을 mockup에서 배포 가능한 서비스로 전환하기 위한
핵심 아키텍처 결정을 기록한다. 각 결정은 향후 변경 시 본 문서를 업데이트한다.

작성일: 2026-05-04
상태: 진행 중 (Phase 0 시작)

---

## ADR-001. 본 프로젝트의 스코프

**결정**: 본 프로젝트는 **수집된 데이터를 활용하는 심사 워크플로 웹 서비스**에
한정한다. 데이터 수집은 별도 프로젝트로 분리한다.

| 영역 | 본 프로젝트 (IN) | 별도 프로젝트 (OUT) |
|---|---|---|
| 인증/사용자 | O | |
| 대출 신청 (대부업체) | O | |
| 사후 모니터링 (심사역) | O | |
| AI 분석 (Claude) | O | |
| 단지/시세/거래/매물 조회 | O (read-only) | |
| KB/MOLIT 수집 | | O |
| crawl_jobs / runs / batches | | O |
| 단지 등록·수정 | | O |

**근거**: 책임 분리. 수집기는 백그라운드/배치 워크로드, 웹은 사용자 대면 트랜잭션.
서로 다른 SLA·확장 패턴.

---

## ADR-002. 수집 DB와의 관계: 동일 PostgreSQL 공유 (옵션 A)

**결정**: 초기에는 수집기와 본 앱이 **동일 PostgreSQL 인스턴스를 공유**한다.
- 수집기: `complexes`, `areas`, `kb_prices`, `transactions`, `listings`,
  `crawl_jobs`, `crawl_runs`, `crawl_tasks`, `raw_payloads` 테이블 소유 (읽기/쓰기)
- 본 앱: `users`, `loan_applications`, `monitoring_loans`, `search_history`,
  `analysis_audit_logs` 테이블 소유 (읽기/쓰기)
- 본 앱은 수집기 소유 테이블을 **read-only**로 참조

**대안 검토**:
- B) 별도 DB + ETL/CDC: 운영 복잡도가 초기 단계에 과함
- C) 수집기 API 호출: 분석 응답 지연 발생 가능

**향후 전환 트리거**: 트래픽이 수집 워크로드와 충돌하거나 보안 요건상 격리 필요 시.

**구현 영향**:
- Alembic 마이그레이션은 본 앱 소유 테이블만 관리
- KB 데이터 모델은 본 앱에서 SQLAlchemy 모델만 유지 (ORM 매핑 목적), CREATE TABLE은 수집기가 수행

---

## ADR-003. 수집 코드의 격리 방식

**결정**: 수집 관련 코드는 **삭제하지 않고** `backend/_to_extract/` 디렉토리로
이동시켜 추후 별도 레포로 추출한다.

**대상**:
- `backend/connectors/` (KB API 커넥터)
- `backend/browser/` (Playwright 세션)
- `backend/workers/` (Celery 태스크)
- `backend/services/sync_collector.py`
- `backend/services/complex_discovery.py`
- `backend/routers/jobs.py`, `runs.py`, `batches.py`, `data_explorer.py`
- `backend/seed_*.py` (초기 시드 — 수집기 책임)

**유지** (read-only로 본 앱에서 사용):
- `backend/models/complex.py`, `crawl.py`, `price_data.py` (ORM 모델)
- `backend/routers/complexes.py` 의 GET 엔드포인트만 (수집 트리거 엔드포인트는 Phase 1에서 분리)

**근거**: 사용자가 별개 프로젝트로 만들 예정이므로 자산 보존이 중요.

---

## ADR-004. 권한 모델: 3-tier RBAC

**결정**: `customer / auditor / admin` 3-tier로 시작.

- `customer`: 대부업체 담당자. 자기 회사의 신청 CRUD만 가능
- `auditor`: 심사역 (JB우리캐피탈). 모든 신청 조회·심사 처리, 모니터링
- `admin`: 사용자 관리, 통계, 시스템 설정

**멀티테넌시는 지금 도입하지 않음**. `loan_applications`에 `applicant_id`로
사용자 격리. 향후 회사/조직 단위 분리 필요 시 `tenant_id` 컬럼 추가.

**구현**: FastAPI Dependency로 `require_role(["auditor", "admin"])` 같은 가드 제공.

---

## ADR-005. 인증: JWT (Access only, 1근무일 만료)

**결정**:
- 패스워드: **bcrypt** 해싱
- 토큰: JWT (HS256), Access Token만, **만료 8시간 (480분)**
- 저장: 프론트엔드 **메모리 + httpOnly 쿠키 옵션** (XSS 방지)
- Refresh token은 단계 2에서 검토 (지금은 8시간 후 재로그인 허용)

**근거**: 단순성. 60분 초기 정책은 심사역이 한 건 분석 중에도 강제 로그아웃되어 운영 불만 누적 → 한 근무일(8h) 로 완화. Refresh 도입은 사내 보안 정책·재로그인 빈도 운영 데이터 확인 후 검토.

**변경 이력**:
- 2026-05-11: 60분 → 480분 (8시간). 심사역 작업 흐름 보호 + 사내 도구/HTTPS/짧은 액세스 토큰 가정에서 노출 위험 한정적.

---

## ADR-006. 신청 부가기능 도입 순서

**결정**: 대출 신청은 **단계적**으로 기능 추가:

| 시점 | 추가 기능 |
|---|---|
| Phase 2 초반 | 상태 머신 (접수 → 심사중 → 승인/반려/보류), 메모, 심사역 배정 |
| Phase 2 중반 | 첨부파일 업로드 (등기부등본 PDF, 사업자등록증 등) |
| Phase 2 후반 | 알림 (이메일 → 추후 SMS/카카오 검토) |

**파일 저장**: 초기는 로컬 파일시스템 + presigned-style URL, 운영은 S3 호환 (config.py에 이미 옵션 있음).

---

## ADR-007. 배포: Docker 기반 PaaS-friendly

**결정**:
- 컨테이너: `backend` (FastAPI), `frontend` (nginx + 정적 파일), `postgres`, `redis`
- 빌드: 멀티스테이지 Dockerfile (의존성 레이어 캐시, 최종 이미지 슬림화)
- docker-compose: dev 환경 일체 기동
- 운영: PaaS (Railway / Fly.io / Cloudtype) 또는 자체 서버 (docker-compose) 모두 가능
- 환경 분리: `.env` 파일 + 운영은 PaaS Secrets

**CI/CD**: Phase 6에서 GitHub Actions (lint → test → build image → deploy)

---

## ADR-008. AI 분석 운영

**결정**:
- 제공자: **OpenAI** (사용자 결정, 2026-05-04). API 키는 사용자가 제공
- 모델: 시작은 **gpt-4o** (env `OPENAI_MODEL`로 변경 가능, 예: `gpt-4o-mini`로 비용 절감)
- SDK: `openai` Python 패키지 (`backend/services/llm_service.py`로 추상화)
- 호출: 동기 호출 (분석 요청 → 응답 대기). 평균 응답 < 30초 목표
- 재시도: 1회 (5xx, timeout 시), 그 이상은 사용자에게 에러
- **감사 로그**: 모든 분석 호출의 입력/모델/응답/소요시간을 `analysis_audit_logs.llm_model` 등에 영속화
- 캐싱: 동일 (회사명, 주소, 대출금액) 조합 24시간 Redis 캐시
- 비용 한도: 일일 호출 수 cap (`LLM_DAILY_CALL_LIMIT`)

**향후 모델 교체**: `LLMClient`는 OpenAI ChatCompletion에 구현. 다른 제공자로 교체 시
같은 인터페이스(`complete(prompt, system=...) -> dict`)를 유지한 채 내부만 갈아끼움.

---

## ADR-009. 관측성

**결정**:
- 에러 추적: **Sentry** (BE/FE) — DSN env로 주입, 미설정 시 비활성
- 로깅: 구조화 JSON (`core/logging.py` 활용), stdout으로 출력 (PaaS log 수집)
- 메트릭: 최소 Prometheus `/metrics` 엔드포인트 (Phase 5)
- 헬스체크: `/api/health/live` (process), `/api/health/ready` (DB/Redis 연결)

---

## ADR-010. 컴플라이언스 / PII

**결정**:
- 마스킹: 다른 프로젝트 자산(`filter_pii_masking_v3.py`) 참고하여 본 앱에 통합
- 저장 시 암호화: 패스워드 해싱은 필수, 차주/보증인 주민번호 등은 도메인상 평문 저장 불가 → 암호화 또는 마스킹 후 저장
- 약관/개인정보 처리방침: 운영 직전 단계에서 작성 (법무 검토 필요)
- Claude 호출 시: 최소 필요 정보만 전송, PII 식별자는 마스킹

**보존 정책**:
- 분석 감사 로그: 5년 (금융권 표준)
- 인증 로그: 1년
