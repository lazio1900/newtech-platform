# CLAUDE.md — newtech-platform

이 파일은 본 레포(`newtech-platform`)에서 에이전트(Claude Code 등)가 따라야 할
**빌드 / 코딩 / 커밋 규칙**과 **반복 실수 차단 지시**를 모은다.

> 짝 프로젝트 `newtech_data`(KB 수집기)와의 관계, DB·포트 할당은 `INTEGRATION.md`
> 와 `docs/architecture-decisions.md`(ADR-001~010)를 단일 출처로 한다. 충돌이
> 생기면 그 두 문서가 우선.

---

## 1. 프로젝트 개요 (요약)

- 목적: JB우리캐피탈 질권 담보 대출 **심사 워크플로 웹 서비스**
- 스코프: 사용자/심사/모니터링/AI 분석/단지·시세 조회(read-only). **데이터 수집은 본 레포 책임 아님** (ADR-001)
- 짝 프로젝트: `newtech_data` (KB부동산 수집) — 같은 PostgreSQL(5433) 공유 (ADR-002)

## 2. newtech_data 와의 관계 (필독)

본 앱은 단독으로 동작하지 않는다. KB부동산 수집기 `newtech_data` 와 **같은
PostgreSQL 한 대를 공유**하면서, 본 앱은 단지/시세/실거래/매물 데이터를
**read-only 로만** 참조한다. 이 관계가 깨지면 분석 화면은 더미 데이터로 떨어진다.

### 2.1 역할 분담

| 항목 | newtech-platform (이 레포) | newtech_data |
|---|---|---|
| 위치 | `/Users/lmj/00_projects/newtech-platform` | `/Users/lmj/00_projects/newtech_data/kb-estate-collector` |
| 책임 | 심사 워크플로 웹 서비스 (사용자/신청/심사/모니터링/AI) | KB부동산 크롤링·적재 |
| 사용자 대면 | O (FastAPI 8002 + Frontend 5173) | 운영 콘솔 (FastAPI 8000 + Frontend 5174) |
| Celery / 백그라운드 수집 | X | O |

### 2.2 공유 인프라 (본 레포의 docker-compose 가 책임)

- **PostgreSQL**: 5433 / DB `kb_estate` / user `kb_user`
- **Redis**: 6379 / DB 0

`newtech_data` 의 `docker-compose.yml` 에도 postgres/redis 정의가 있지만
**사용하지 않는다.** 본 레포 compose 만 인프라를 띄우고, `newtech_data` 는
호스트의 5433/6379 에 붙는다. 양쪽이 동시에 인프라를 띄우면 컨테이너 이름·포트
충돌이 발생한다.

### 2.3 DB 테이블 소유권 (ADR-002 단일 출처)

| 소유자 | 테이블 | 본 앱의 접근 |
|---|---|---|
| **newtech-platform** | `users`, `loan_applications`, `monitoring_loans`, `search_history`, `analysis_audit_logs` | 읽기·쓰기 |
| **newtech_data** | `complexes`, `areas`, `kb_prices`, `transactions`, `listings`, `crawl_jobs`, `crawl_runs`, `crawl_tasks`, `raw_payloads` | **read-only** |

본 앱이 수집기 소유 테이블에 INSERT/UPDATE/DELETE 하거나 Alembic 마이그레이션을
만드는 것은 **금지**. 스키마 변경이 필요하면 `newtech_data` 쪽에서 먼저 수행하고
본 앱은 SQLAlchemy 모델만 동기화한다 (`backend/models/complex.py`, `crawl.py`,
`price_data.py`).

### 2.4 Alembic 분리

- 본 앱 version_table: **`alembic_version_app`**
- newtech_data version_table: `alembic_version` (default)
- 같은 DB 안에 두 개의 alembic 히스토리가 공존하므로 version_table 명을 절대
  바꾸지 말 것.

### 2.5 기동 순서 / 데이터 흐름

```
[1] 본 레포: docker compose up -d postgres redis   ← 인프라 책임
[2] 본 레포: backend (8002) + frontend (5173)
[3] newtech_data: admin API (8000) + Celery + frontend (5174)
[4] newtech_data 콘솔에서 단지 등록·수집 → kb_estate DB 적재
[5] 본 앱 audit 화면이 그 데이터를 read-only 매칭하여 분석에 사용
```

`newtech_data` 없이도 본 앱은 뜨지만, 단지·시세 매칭이 안 되어 분석이
더미 응답으로 떨어진다 (`services/dummy_data.py` 폴백). 분석 화면을 다룰 때는
수집기까지 함께 띄워 검증한다 (`docs/run-guide.md` §D).

### 2.6 본 앱에서 분리해 둔 수집기 자산

`backend/_to_extract/` 에 수집기 관련 코드(`connectors/`, `browser/`, `workers/`,
`sync_collector.py`, `complex_discovery.py`, `jobs.py`, `runs.py`, `batches.py`,
`data_explorer.py`, `seed_*.py`)를 보존해 두었다. 추후 `newtech_data` 로 이관할
자산이므로 **수정·삭제·이동 금지** (ADR-003).

### 2.7 관련 문서

- `INTEGRATION.md` — 포트·DB 소유권 표 (단일 출처)
- `docs/architecture-decisions.md` ADR-001~003 — 스코프 분리 / 동일 PG 공유 / 수집 코드 격리
- `docs/run-guide.md` §D — 수집기 함께 띄우는 절차

---

## 3. 디렉토리 구조

```
backend/        # FastAPI 앱 (Python 3.x, SQLAlchemy 2, Alembic)
  core/         # config, database, auth, security, logging
  models/       # SQLAlchemy ORM
  routers/      # API 엔드포인트 (도메인별 분리)
  services/     # 비즈니스 로직 / AI / 데이터 매칭
  alembic/      # 마이그레이션 (App 소유 테이블만)
  scripts/      # 시드 등 운영 스크립트 (운영 실행 금지 항목 있음)
  _to_extract/  # 추후 newtech_data 로 떼낼 수집 코드 (건드리지 않음, ADR-003)
frontend/       # React 19 + Vite + TS, axios, react-query, leaflet, recharts
docs/           # ADR, run-guide, project-structure 등 — 단일 출처
docker-compose.yml
INTEGRATION.md  # newtech_data 연동 / 포트·DB 소유권
```

## 4. 빌드 / 실행

자세한 절차는 `docs/run-guide.md`. 핵심만:

### 포트 (고정 — 임의 변경 금지, INTEGRATION.md §포트 할당)
| 서비스 | 포트 |
|---|---|
| PostgreSQL (공유) | 5433 |
| Redis (공유) | 6379 |
| **newtech-platform** Backend | **8002** |
| **newtech-platform** Frontend | **5173** |
| newtech_data Backend | 8000 |
| newtech_data Frontend | 5174 |

### 일체형 (docker compose)
```bash
cp .env.example .env
cp backend/.env.example backend/.env   # JWT_SECRET_KEY 교체
docker compose up -d --build
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_users.py   # 개발용
```

### 로컬 개발
```bash
docker compose up -d postgres redis       # 인프라만
cd backend && source .venv/bin/activate
uvicorn main:app --reload --port 8002
cd ../frontend && npm run dev              # http://localhost:5173
```

### 마이그레이션
- 본 앱 alembic 의 `version_table` 은 **`alembic_version_app`** (newtech_data 의 default `alembic_version` 과 충돌 방지)
- 본 앱은 **App 소유 테이블만** 마이그레이션 (ADR-002). 수집기 소유 테이블(`complexes`, `areas`, `kb_prices`, `transactions`, `listings`, `crawl_*`, `raw_payloads`)에는 손대지 않는다.

### Lint / 빌드 검증
- Backend: 별도 lint 도구 미구성. 변경 시 `python -c "import main"` 또는 `uvicorn` 기동으로 import 에러 확인
- Frontend: `npm run lint`, `npm run build` (tsc -b → vite build) 가 통과해야 함

## 5. 코딩 규칙

### 공통
- **지정 파일만 수정한다.** 사용자가 지목하지 않은 파일·디렉토리는 백업/참고용으로 간주하고 건드리지 않는다. 특히 `backend/_to_extract/` 는 newtech_data 로 떼낼 자산이므로 **수정·삭제 금지** (ADR-003).
- **목업의 모든 항목을 강제로 구현하지 않는다.** 핵심 기능이 충분하면 생략 판단을 먼저 제시하고 사용자의 동의를 받는다.
- 사용자 요청 범위 밖의 리팩토링·정리·추상화 도입은 하지 않는다. 같은 줄 3번 반복이 섣부른 추상화보다 낫다.
- 외부 경계(사용자 입력, 외부 API)가 아닌 곳에는 방어 코드·폴백·검증을 추가하지 않는다. 내부 호출과 프레임워크 보증은 신뢰한다.
- 주석은 기본적으로 쓰지 않는다. **왜**가 비자명할 때만 한 줄로. 코드가 무엇을 하는지는 식별자로 설명한다.

### 백엔드 (FastAPI / SQLAlchemy)
- 라우터 path 는 **trailing slash 없이** 일관 사용 (main.py: `redirect_slashes=False`).
- 새 라우터는 `routers/` 에 추가하고 `main.py` 에 `include_router` 등록.
- 비즈니스 로직은 `services/` 로 분리. 라우터는 IO + 검증 + service 호출에 한정.
- DB 세션은 `core/database.py` 의 의존성 사용. 라우터/서비스에서 새 engine 생성 금지.
- 수집기 소유 테이블은 **read-only**. INSERT/UPDATE/DELETE 금지 (ADR-002).
- 모델 변경 → `alembic revision --autogenerate -m "..."` → 사람이 검토 후 `upgrade head`. autogenerate 결과 그대로 커밋하지 말고 잡음(noise) 제거.
- AI 호출은 `services/llm_service.py` 의 `LLMClient` 인터페이스를 거친다. 라우터/타 서비스에서 OpenAI SDK 직접 호출 금지 (ADR-008).
- PII (주민번호 등)는 평문 저장 금지, AI 호출 시 마스킹 (ADR-010).
- 인증: bcrypt + JWT(HS256, Access only 8시간). `core/auth.py` 의 의존성/가드 재사용 (ADR-004, 005).

### 프론트엔드 (React 19 / Vite / TS)
- API 호출은 `src/api/` 의 axios 클라이언트 + `@tanstack/react-query` 훅으로 통일. 컴포넌트에서 fetch 직접 호출 금지.
- 환경변수는 `VITE_*` 접두사. `VITE_API_BASE_URL` 은 **빈 값 유지** (dev 는 vite proxy, prod 는 nginx 가 `/api` 를 backend 로 프록시).
- 타입: `src/types/` 의 정의 재사용. 라우터 응답 모델이 바뀌면 양쪽 동기화.
- 지도/차트: leaflet, recharts. 새 라이브러리 추가 전에 기존 의존성으로 가능한지 먼저 확인.

## 6. 커밋 규칙

기존 로그 스타일 (한국어, 짧은 요약):
```
commit 2026-05-08 : 등기부등본 등 전반 개선 & 디자인 처리 전 커밋
심사 화면 UI 개선: 섹션 구분, 유사 물건 목록, 차트 오토스케일
```

원칙:
- **사용자가 명시적으로 커밋을 지시할 때만** 커밋한다. 작업 종료 시 자동 커밋 금지.
- 한 줄 요약은 변경의 **목적/도메인** 중심 (예: "심사 화면 UI 개선", "AI 분석 캐시 도입"). "what" 보다 "why".
- `.env`, 시크릿, 대용량 바이너리는 staging 금지. `git add -A` / `git add .` 지양, 파일 단위 추가.
- pre-commit hook 실패 시 **amend 하지 않고** 새 커밋으로 수정. (--no-verify 금지)
- 푸시는 명시적 지시가 있을 때만.

## 7. 반복 실수 차단 (Anti-patterns)

> **이 섹션은 살아있는 체크리스트다.** 같은 실수가 두 번째로 나오면 여기에 추가한다.
> 형식: `### N. <한 줄 규칙>` + **상황** / **하지 말 것** / **할 것** 세 줄.

### 1. 수집기 소유 테이블에 마이그레이션을 만들지 말 것
- **상황**: 모델 변경 후 `alembic revision --autogenerate` 시 `complexes` / `kb_prices` 등이 diff 에 포함됨
- **하지 말 것**: 그대로 커밋. version_table 도 충돌남.
- **할 것**: autogenerate 결과에서 수집기 테이블 관련 op 모두 제거. 본 앱 마이그레이션은 `alembic_version_app` 만 쓴다. 스키마 변경이 정말 필요하면 newtech_data 쪽에 먼저 만들고 본 앱 ORM 만 동기화. (ADR-002)

### 2. 포트를 임의로 바꾸지 말 것
- **상황**: 포트 충돌 에러 → 다른 포트로 변경 유혹
- **하지 말 것**: 8002/5173/5433/6379 변경, INTEGRATION.md 미수정.
- **할 것**: 무엇이 그 포트를 점유했는지 먼저 확인(`lsof -i :8002`). 짝 프로젝트(newtech_data) 가 띄워둔 중복 인프라일 가능성이 큼.

### 3. `_to_extract/` 를 건드리지 말 것
- **상황**: import 에러나 lint 경고가 거기서 발생
- **하지 말 것**: 파일 수정·삭제·이동.
- **할 것**: 본 앱이 import 하고 있다면 import 경로를 본 앱 쪽으로 옮기는 게 맞다. `_to_extract/` 자체는 그대로 둔다. (ADR-003)

### 4. trailing slash 라우트를 새로 만들지 말 것
- **상황**: 신규 라우터에 `@router.get("/")` 식으로 작성
- **하지 말 것**: 308 redirect 가 nginx 환경에서 host:port 깨짐.
- **할 것**: `redirect_slashes=False` 가 켜져 있으므로 라우트 path 는 trailing slash 없이 작성 (`/applications`, `/applications/{id}` 형식).

<!-- 다음 항목 추가 양식
### N. <한 줄 규칙>
- **상황**:
- **하지 말 것**:
- **할 것**:
-->

## 8. 단일 출처 (Source of Truth)

| 주제 | 문서 |
|---|---|
| 전체 아키텍처 결정 | `docs/architecture-decisions.md` (ADR-001~010) |
| 실행/배포 절차 | `docs/run-guide.md` |
| newtech_data 연동·포트·DB 소유권 | `INTEGRATION.md` |
| 디렉토리 구조 상세 | `docs/project-structure.md` |
| 다음 작업 / 우선순위 | `docs/next-tasks.md` |

본 CLAUDE.md 와 위 문서가 충돌하면 **위 문서가 우선**한다. 본 파일은 에이전트용 규칙 모음일 뿐, 결정 기록은 ADR 에 둔다.
