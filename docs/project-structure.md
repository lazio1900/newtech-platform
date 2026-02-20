# 프로젝트 구조

## 디렉토리 레이아웃
```
newtech_merge/
├── docker-compose.yml          # PostgreSQL 14 + Redis 7
├── .gitignore
├── backend/
│   ├── main.py                 # FastAPI 앱 + 인라인 라우트 (analyze, login, register, applications, monitoring)
│   ├── .env                    # DATABASE_URL, ANTHROPIC_API_KEY
│   ├── requirements.txt
│   ├── core/
│   │   ├── config.py           # Settings (DB포트 5433, Redis, KB rate limit 등)
│   │   ├── database.py         # SQLAlchemy engine + SessionLocal
│   │   └── logging.py
│   ├── models/
│   │   ├── complex.py          # Complex, Area 모델
│   │   ├── price_data.py       # KBPrice, Transaction, Listing 모델
│   │   ├── crawl.py            # CrawlJob, CrawlRun, CrawlTask, RawPayload 모델
│   │   └── response_models.py  # API 응답 Pydantic 모델 (AnalysisResponse 등)
│   ├── routers/
│   │   ├── complexes.py        # /api/complexes/* (CRUD, discover, collect, batch)
│   │   ├── jobs.py             # /api/jobs/* (BackgroundTasks로 실행)
│   │   ├── runs.py             # /api/runs/* (실행 이력)
│   │   ├── batches.py          # /api/batches/* (지역별 배치)
│   │   └── data_explorer.py    # /api/data/* (KB시세, 거래, 매물 조회/내보내기)
│   ├── services/
│   │   ├── analysis_service.py # perform_full_analysis() - 실제+더미 하이브리드
│   │   ├── real_data_service.py# DB에서 실제 수집 데이터 조회
│   │   ├── dummy_data.py       # 랜덤 더미 데이터 생성기
│   │   ├── sync_collector.py   # collect_complex_sync() - KB 데이터 수집 실행
│   │   ├── complex_discovery.py# ComplexDiscoveryService - 지역 기반 단지 자동 발견
│   │   ├── auth_store.py       # 인메모리 인증 (하드코딩)
│   │   ├── application_store.py# 인메모리 대출 신청 (더미 3건)
│   │   ├── monitoring_store.py # 인메모리 모니터링 (더미 8건)
│   │   ├── history_store.py    # 인메모리 검색 이력 (더미)
│   │   └── claude_service.py   # Claude API (현재 미사용, 하드코딩된 분석문)
│   ├── connectors/
│   │   ├── kb_base.py          # KB API 기본 (HTTP + Playwright 폴백)
│   │   ├── kb_price.py         # KB 시세 API
│   │   ├── kb_transaction.py   # KB 거래 API
│   │   ├── kb_listing.py       # KB 매물 API
│   │   ├── kb_endpoints.py     # KB API 엔드포인트 정의
│   │   └── molit_transaction.py# 국토부 실거래 API
│   ├── browser/
│   │   ├── session_manager.py  # Playwright 브라우저 세션
│   │   ├── stealth.py          # 봇 탐지 우회
│   │   └── api_discovery.py    # KB JS 번들 분석
│   └── workers/
│       └── tasks.py            # Celery 태스크 정의 (현재 미사용)
├── frontend/
│   ├── package.json            # React 19, Vite 7, TanStack Query 5, Recharts, Leaflet
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── App.tsx             # Login → CustomerDashboard / AuditorDashboard
│       ├── main.tsx            # QueryClientProvider
│       ├── api/
│       │   ├── client.ts       # Axios baseURL=localhost:8000
│       │   ├── analysis.ts     # analyzeProperty(), getSuggestions()
│       │   ├── auth.ts         # login(), register()
│       │   ├── applications.ts # 대출 신청 CRUD
│       │   ├── monitoring.ts   # 모니터링 대출 조회/등록
│       │   ├── complexes.ts    # 단지 CRUD, discover, collect, batch
│       │   ├── jobs.ts         # 수집 작업 관리
│       │   ├── runs.ts         # 실행 이력
│       │   ├── batches.ts      # 배치 관리
│       │   └── data.ts         # KB시세/거래/매물 조회
│       ├── types/
│       │   ├── loan.ts         # User, LoanApplication, AnalysisResponse 등
│       │   ├── complex.ts      # Complex, Area, PriorityLevel
│       │   ├── job.ts          # CrawlJob, JobType, JobStatus
│       │   ├── run.ts          # CrawlRun, CrawlTask, RunStatus
│       │   ├── batch.ts        # Batch
│       │   └── data.ts         # KBPrice, Transaction, Listing
│       ├── hooks/
│       │   ├── useComplexes.ts # useComplexes, useBatchDiscoverRegion 등
│       │   └── useData.ts      # useKBPrices, useTransactions, useListings
│       └── components/
│           ├── AuditorDashboard.tsx   # 심사역 메인 (7개 탭)
│           ├── AuditorDashboard.css
│           ├── CustomerDashboard.tsx  # 고객 대시보드
│           ├── LoginPage.tsx
│           ├── RegisterPage.tsx
│           ├── MonitoringTab.tsx      # 사후모니터링
│           ├── InputSection.tsx       # 분석 입력 폼
│           ├── BorrowerInfo.tsx       # 차주 정보
│           ├── GuarantorInfo.tsx      # 보증인 정보
│           ├── PropertyBasicInfo.tsx  # 물건 기본정보
│           ├── PropertyRightsInfo.tsx # 등기 권리관계
│           ├── CreditSources.tsx     # 시세 출처 (KB/국토부/네이버)
│           ├── PriceCharts.tsx       # 시세 차트
│           ├── PricePerPyeongChart.tsx# 평당가 추이
│           ├── AIPropertyAnalysis.tsx # AI 물건분석
│           ├── AIRightsAnalysis.tsx   # AI 권리분석
│           ├── AIMarketAnalysis.tsx   # AI 시장분석
│           ├── AiComprehensiveOpinion.tsx # AI 종합의견
│           ├── LtvCalculation.tsx     # LTV 계산
│           ├── NearbyPropertyMap.tsx  # 유사물건 지도 (Leaflet)
│           ├── NearbyPropertyList.tsx # 유사물건 목록
│           ├── RegistryModal.tsx      # 등기부 모달
│           ├── AutocompleteInput.tsx  # 주소 자동완성
│           └── collector/
│               ├── CollectorDashboard.tsx # 수집 관리 메인
│               ├── ComplexList.tsx        # 단지 목록 + 지역발견 모달
│               ├── ComplexDetail.tsx      # 단지 상세 + 서브탭
│               ├── ComplexFormModal.tsx   # 단지 등록/수정
│               ├── BatchSettings.tsx     # 배치 설정
│               ├── PriceTab.tsx          # 시세 탭
│               ├── TransactionTab.tsx    # 거래 탭
│               ├── ListingTab.tsx        # 매물 탭
│               ├── RunList.tsx           # 실행 이력
│               ├── RunDetail.tsx         # 실행 상세
│               ├── DataExplorer.tsx      # 데이터 탐색
│               ├── Pagination.tsx
│               └── StatusBadge.tsx
```

## API 엔드포인트 전체 목록

### main.py 인라인 라우트
| Method | Path | 설명 | 데이터 소스 |
|--------|------|------|-------------|
| POST | /api/analyze | 담보 분석 | 하이브리드 (DB우선→더미폴백) |
| POST | /api/login | 로그인 | 인메모리 하드코딩 |
| POST | /api/register | 회원가입 | 인메모리 |
| GET | /api/suggestions | 자동완성 | 인메모리 더미 |
| POST | /api/applications | 대출 신청 | 인메모리 더미 |
| GET | /api/applications | 신청 목록 | 인메모리 더미 |
| PUT | /api/applications/{id}/status | 상태 변경 | 인메모리 |
| GET | /api/monitoring | 모니터링 목록 | 인메모리 더미 |
| POST | /api/monitoring | 모니터링 등록 | 인메모리 |

### routers/complexes.py — 실제 DB
| Method | Path | 설명 |
|--------|------|------|
| GET | /api/complexes | 단지 목록 (페이징, 검색) |
| POST | /api/complexes | 단지 등록 |
| GET | /api/complexes/{id} | 단지 상세 |
| PATCH | /api/complexes/{id} | 단지 수정 |
| DELETE | /api/complexes/{id} | 단지 삭제 |
| GET | /api/complexes/region-counts | 지역별 단지 수 |
| GET | /api/complexes/last-runs | 단지별 마지막 수집 상태 |
| GET | /api/complexes/regions/sigungu | 시군구 목록 (KB API) |
| POST | /api/complexes/discover-region | 지역 발견 (KB에서 단지 검색) |
| POST | /api/complexes/{id}/collect | 단일 수집 |
| POST | /api/complexes/batch-collect | 일괄 수집 |
| GET | /api/complexes/runs/{run_id}/status | 수집 진행 상태 |

### routers/jobs.py, runs.py, batches.py, data_explorer.py — 실제 DB
| Method | Path | 설명 |
|--------|------|------|
| GET/POST | /api/jobs | 작업 목록/생성 |
| POST | /api/jobs/create-and-run | 작업 생성 즉시 실행 |
| POST | /api/jobs/{id}/run | 작업 실행 |
| GET | /api/runs | 실행 이력 |
| GET | /api/runs/{id}/tasks | 실행 태스크 상세 |
| GET | /api/batches | 배치 목록 |
| GET | /api/data/kb-prices | KB 시세 조회 |
| GET | /api/data/transactions | 거래 조회 |
| GET | /api/data/listings | 매물 조회 |
| GET | /api/data/kb-prices/export | CSV 내보내기 |

## DB 모델 (SQLAlchemy)
```
Complex (complexes) ─1:N─ Area (areas)
Complex ─1:N─ KBPrice (kb_prices) ─ via area_id
Complex ─1:N─ Transaction (transactions)
Complex ─1:N─ Listing (listings)
CrawlJob (crawl_jobs) ─1:N─ CrawlRun (crawl_runs)
CrawlRun ─1:N─ CrawlTask (crawl_tasks)
CrawlTask ─1:N─ RawPayload (raw_payloads)
```

## 외부 API
- **KB부동산** (`api.kbland.kr`): 단지검색, 상세, 면적, 시세, 거래, 매물
- **국토부 (MOLIT)**: 실거래가
- **Anthropic Claude**: AI 분석 (현재 미사용, 하드코딩된 텍스트)
