# newtech-platform ↔ newtech_data 연동 가이드

## 역할

| 프로젝트 | 역할 | 경로 |
|----------|------|------|
| **newtech-platform** (이 프로젝트) | 사용자 서비스 (대출심사 플랫폼) | `/Users/lmj/00_projects/newtech-platform` |
| **newtech_data** | 데이터 수집 (KB부동산 크롤링) | `/Users/lmj/00_projects/newtech_data/kb-estate-collector` |

## 공유 인프라

두 프로젝트는 **하나의 PostgreSQL과 Redis**를 공유합니다.
인프라는 이 프로젝트(`newtech-platform`)의 docker-compose에서 통합 관리합니다.

| 서비스 | 포트 | DB/유저 |
|--------|------|---------|
| PostgreSQL | **5433** | `kb_estate` / `kb_user` |
| Redis | **6379** | DB 0 |

## 포트 할당 (고정)

| 서비스 | 포트 | 프로젝트 |
|--------|------|----------|
| PostgreSQL | 5433 | 공유 |
| Redis | 6379 | 공유 |
| **newtech-platform** Backend (FastAPI) | **8002** | 이 프로젝트 |
| **newtech-platform** Frontend | **5173** | 이 프로젝트 |
| **newtech_data** Backend (FastAPI) | **8000** | newtech_data |
| **newtech_data** Frontend (Vite) | **5174** | newtech_data |
| Celery Worker | - (포트 없음) | newtech_data |

## DB 테이블 소유권

### 이 프로젝트 소유 (App)
서비스 로직 테이블. 읽기/쓰기 모두 이 프로젝트에서 관리.

| 테이블 | 설명 |
|--------|------|
| `users` | 사용자 계정 (CUSTOMER, AUDITOR, ADMIN) |
| `loan_applications` | 대출 심사 신청 |
| `monitoring_loans` | 실행 후 모니터링 |
| `search_history` | 검색 자동완성 |
| `analysis_audit_logs` | AI 분석 감사 로그 |

### newtech_data 소유 (Collector) — 읽기 전용 참조
이 프로젝트는 아래 테이블을 **읽기 전용**으로 참조합니다.
스키마 변경은 newtech_data에서만 수행합니다.

| 테이블 | 설명 | 활용 |
|--------|------|------|
| `complexes` | 아파트 단지 정보 | 단지 검색/매칭 |
| `areas` | 단지별 면적 타입 | 면적 조회 |
| `kb_prices` | KB 시세 데이터 | 시세 분석, LTV 산정 |
| `transactions` | 실거래가 | 실거래 분석 |
| `listings` | 매물 정보 | 호가 분석 |
| `crawl_jobs` | 수집 작업 | (참조 불필요) |
| `crawl_runs` | 수집 실행 이력 | (참조 불필요) |
| `crawl_tasks` | 수집 태스크 | (참조 불필요) |
| `raw_payloads` | 원문 스냅샷 | (참조 불필요) |

## 이 프로젝트 설정

```env
# backend/.env
DATABASE_URL=postgresql://kb_user:kb_password@localhost:5433/kb_estate
REDIS_URL=redis://localhost:6379/0
API_PORT=8002
CORS_ORIGINS=http://localhost:5173
```

## 기동 순서

```bash
# 1. 인프라 (이 프로젝트에서 관리)
docker-compose up -d postgres redis

# 2. 이 프로젝트
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload

# 3. 프론트엔드 (별도 터미널)
cd frontend && npm run dev
# → http://localhost:5173

# 4. newtech_data (필요 시, 별도 터미널)
cd /Users/lmj/00_projects/newtech_data/kb-estate-collector
source .venv/bin/activate
uvicorn src.admin_api.main:app --host 0.0.0.0 --port 8000 --reload
# → http://localhost:5174 (프론트엔드)
```

## 데이터 흐름

```
newtech_data (수집)                    newtech-platform (서비스)
━━━━━━━━━━━━━━━━━━━                   ━━━━━━━━━━━━━━━━━━━━━━━
KB부동산 API                           사용자 (고객/심사역)
     │                                       │
     ▼                                       ▼
Celery Worker                          FastAPI (8002)
     │                                       │
     ▼                                       ▼
┌─────────────────── PostgreSQL (5433) ───────────────────┐
│                      kb_estate DB                        │
│                                                          │
│  [Collector 소유]          [App 소유]                    │
│  complexes ───────────→ loan_applications               │
│  kb_prices ───────────→ monitoring_loans                │
│  transactions ────────→ analysis_audit_logs             │
│  listings                users                           │
│  crawl_*                 search_history                  │
└──────────────────────────────────────────────────────────┘
```

## 주의사항

- **마이그레이션**: 각 프로젝트가 자기 소유 테이블만 마이그레이션합니다.
  - newtech_data: `alembic` (complexes, areas, crawl_*, kb_prices, transactions, listings)
  - newtech-platform: `alembic` (users, loan_applications, monitoring_loans 등)
- **포트 충돌 방지**: 위 포트 할당표를 준수합니다. 임의 변경 금지.
- **DB 스키마 충돌 방지**: Collector 테이블 스키마를 변경하려면 newtech_data에서 수행 후 이 프로젝트의 ORM 모델도 동기화합니다.
