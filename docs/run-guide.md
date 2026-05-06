# 실행 가이드

본 앱(`newtech-platform`)을 로컬에서 띄우는 방법. INTEGRATION.md / ADR-002 준수.

> **수집기 데이터**: 단지/시세/실거래/매물 정보는 별도 프로젝트
> [`newtech_data`](file:///Users/lmj/00_projects/newtech_data/kb-estate-collector)
> 가 같은 PostgreSQL에 적재합니다. 분석에서 진짜 단지 데이터를 보려면
> 본 앱과 함께 `newtech_data` 도 띄워야 합니다 ([D. 수집기 함께 띄우기](#d-수집기-함께-띄우기) 참조).

## A. docker-compose (권장: 일체형 기동)

```bash
# 1) compose 변수 준비
cp .env.example .env
# 필요시 POSTGRES_PASSWORD 등 수정

# 2) 백엔드 .env 준비
cp backend/.env.example backend/.env
# JWT_SECRET_KEY는 `openssl rand -hex 32` 결과로 교체 권장 (개발도 권장)
# OPENAI_API_KEY 입력 (Phase 3 이후 필요)

# 3) 빌드 + 기동
docker compose up -d --build

# 4) 스키마 마이그레이션 (한 번만, 또는 모델 변경 시마다)
docker compose exec backend alembic upgrade head

# 5) 시드 사용자 (개발용 — 운영에서는 실행 금지)
docker compose exec backend python scripts/seed_users.py
```

접속:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8002/api/health
- Swagger UI: http://localhost:8002/docs

## B. 로컬 개발 (백엔드/프론트 따로)

전제: PostgreSQL과 Redis가 로컬에 떠 있어야 함. `docker compose up -d postgres redis` 로 인프라만 띄우는 것을 추천.

### 백엔드
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env  # JWT_SECRET_KEY 교체

alembic upgrade head
python scripts/seed_users.py

uvicorn main:app --reload --port 8002
```

### 프론트엔드
```bash
cd frontend
npm install
cp .env.example .env  # VITE_API_BASE_URL은 빈 값 유지(vite proxy 사용)

npm run dev
```

## 기본 시드 계정 (개발용)

| user_id  | password     | role     |
|----------|--------------|----------|
| admin    | admin1234    | admin    |
| audit    | audit1234    | auditor  |
| customer | customer1234 | customer |

운영 배포 전에 `scripts/seed_users.py` 실행 금지. 또는 환경변수로 강한 비밀번호 주입.

## 마이그레이션 워크플로

```bash
# 모델 변경 후 새 revision 생성 (autogenerate)
alembic revision --autogenerate -m "add foo column"

# 적용
alembic upgrade head

# 롤백 (1단계 이전)
alembic downgrade -1

# 현재 버전 확인
alembic current
```

수집기 소유 테이블(complexes, areas, kb_prices 등)은 본 앱 alembic이 관리하지 않음 (ADR-002).
본 앱 alembic 의 version_table 은 **`alembic_version_app`** (newtech_data 의 default
`alembic_version` 과 충돌 방지).

## D. 수집기 함께 띄우기

`newtech_data` 프로젝트가 단지/시세/실거래/매물 데이터를 같은 PostgreSQL 에 적재합니다.
본 앱이 분석 시 그 데이터를 read-only 로 사용합니다.

### D-1. 인프라 (이 프로젝트가 책임)

위 A 또는 B 절차로 본 앱의 docker-compose 가 PostgreSQL(5433) + Redis(6379) 을 띄워야 합니다.
`newtech_data` 의 `docker-compose.yml` 은 자체 postgres/redis 정의가 있지만 **사용하지 않습니다**
(중복 컨테이너 충돌 방지). `newtech_data` 는 호스트의 5433/6379 에 연결합니다.

### D-2. newtech_data 셋업

```bash
cd /Users/lmj/00_projects/newtech_data/kb-estate-collector

# venv 셋업 (한 번만)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# .env 확인 (DATABASE_URL=postgresql://kb_user:kb_password@localhost:5433/kb_estate)
cat .env | grep DATABASE_URL

# alembic 마이그레이션 적용 → collector 테이블 생성
# (newtech_data 의 version_table 은 default `alembic_version`)
alembic upgrade head
```

### D-3. newtech_data 기동

```bash
# Admin API (FastAPI) — 8000 포트
uvicorn src.admin_api.main:app --host 0.0.0.0 --port 8000 --reload

# (선택) Celery worker — 백그라운드 수집 작업
# 별도 터미널
celery -A src.workers.celery_app worker --loglevel=info --concurrency=4

# (선택) Frontend — 5174 포트
cd frontend && npm run dev
```

접속:
- newtech_data Admin API: http://localhost:8000/docs
- newtech_data Frontend: http://localhost:5174

### D-4. 데이터 적재

`newtech_data` Admin Frontend 또는 API 를 사용해 단지를 등록·수집합니다.
자세한 절차는 `newtech_data/README.md` 참조.

### D-5. 본 앱 검증

본 앱 (audit 계정) 에서 신청건 → 상세심사 시, 등록된 단지에 대해서는 실제 KB 시세
및 단지 정보가 매칭되어 표시되어야 합니다.

## 운영 배포 체크리스트

- [ ] `ENVIRONMENT=production`
- [ ] `JWT_SECRET_KEY` = `openssl rand -hex 32` 결과
- [ ] `DATABASE_URL` 의 비밀번호 강한 값으로 교체
- [ ] `CORS_ORIGINS` = 실제 도메인 화이트리스트 (`*` 금지)
- [ ] `SENTRY_DSN` 설정
- [ ] HTTPS / 리버스 프록시 (nginx 또는 PaaS)
- [ ] 시드 스크립트 실행 금지
- [ ] 알렘빅 마이그레이션 적용 후 기동
