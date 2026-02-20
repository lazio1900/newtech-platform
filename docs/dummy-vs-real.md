# 더미 vs 실제 데이터 현황

## 요약표

| 기능 | 현재 상태 | 데이터 소스 | 비고 |
|------|-----------|-------------|------|
| **인증 (로그인/가입)** | DUMMY | `services/auth_store.py` 인메모리 | 하드코딩: customer/1, audit/1 |
| **대출 신청** | DUMMY | `services/application_store.py` 인메모리 | 더미 3건, 서버 재시작 시 초기화 |
| **사후 모니터링** | DUMMY | `services/monitoring_store.py` 인메모리 | 더미 8건, 서버 재시작 시 초기화 |
| **검색 자동완성** | DUMMY | `services/history_store.py` 인메모리 | 더미 업체명 18개, 주소 17개 |
| **차주 정보** | DUMMY | `services/dummy_data.py` | 랜덤 재무제표 생성 |
| **보증인 정보** | DUMMY | `services/dummy_data.py` | 랜덤 신용점수 700~950 |
| **등기 권리관계** | DUMMY | `services/dummy_data.py` | 랜덤 근저당/가압류 |
| **입지 점수** | DUMMY | `services/dummy_data.py` | 랜덤 60~98점 |
| **AI 분석 텍스트** | HARDCODED | `services/analysis_service.py` L178~253 | Claude API 미연동 (주석 처리) |
| **KB/국토부/네이버 시세** | HYBRID | `services/real_data_service.py` | DB 데이터 있으면 실제, 없으면 더미 |
| **유사물건 동향** | HYBRID | `services/real_data_service.py` | 동일 시군구 단지 조회 또는 더미 |
| **평당가 추이** | HYBRID | `services/real_data_service.py` | KB 데이터 또는 더미 |
| **단지 관리 (CRUD)** | REAL | PostgreSQL (complexes) | 완전 DB 기반 |
| **수집 작업/이력** | REAL | PostgreSQL (crawl_jobs/runs/tasks) | 완전 DB 기반 |
| **KB 시세/거래/매물** | REAL | PostgreSQL (kb_prices/transactions/listings) | 수집된 실제 데이터 |
| **지역 발견** | REAL | KB API → PostgreSQL | 실시간 API 호출 |

## 더미→실제 전환 필요 항목

### 1. 인증 시스템 (auth_store.py → DB)
- `users` 테이블 생성 (id, user_id, password_hash, role, company_name 등)
- bcrypt 패스워드 해싱
- JWT 토큰 발급
- 현재 코드: `services/auth_store.py` (인메모리 dict)

### 2. 대출 신청 (application_store.py → DB)
- `loan_applications` 테이블 생성
- 상태 관리: 접수완료 → 심사중 → 승인/반려
- 현재 코드: `services/application_store.py` (인메모리 list, 더미 3건)

### 3. 사후 모니터링 (monitoring_store.py → DB)
- `monitoring_loans` 테이블 생성
- LTV 자동 계산 (KB 시세 연동)
- 경고 신호: green/yellow/red
- 현재 코드: `services/monitoring_store.py` (인메모리 list, 더미 8건)

### 4. AI 분석 (analysis_service.py → Claude API)
- `services/claude_service.py` 이미 존재 (미사용)
- `analysis_service.py` L25~31 주석 해제 + 연동
- 프롬프트: `utils/prompts.py`

### 5. 차주/보증인/등기 정보
- 외부 API 연동 필요 (신용정보, 등기부등본)
- 또는 사용자 직접 입력 UI + DB 저장

### 6. 검색 이력 (history_store.py → DB)
- `search_history` 테이블
- 사용자별 검색 기록 저장

## 분석 서비스 데이터 흐름
```
POST /api/analyze {company, address, loan_amount}
  ↓ main.py (DB optional - 없으면 100% 더미)
  ↓ analysis_service.py::perform_full_analysis()
  ├─ real_data_service.py::get_real_market_data(db, address)
  │   ├─ resolve_complex() — 주소로 Complex 매칭
  │   ├─ build_real_credit_data() — KB/거래/매물 데이터
  │   ├─ build_real_nearby_trends() — 유사물건
  │   └─ build_real_price_per_pyeong() — 평당가 추이
  │   (없으면 None → 더미 폴백)
  ├─ dummy_data.py::generate_borrower_info()     ← 항상 더미
  ├─ dummy_data.py::generate_guarantor_info()     ← 항상 더미
  ├─ dummy_data.py::generate_property_rights_info() ← 항상 더미
  ├─ dummy_data.py::generate_location_scores()    ← 항상 더미
  └─ 하드코딩된 AI 분석 텍스트                     ← 항상 하드코딩
```
