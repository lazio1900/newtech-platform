# 등기부등본 발급 서비스 — 인수인계 문서

> 다른 AI 세션/개발자가 이 문서만 읽고도 현재 상태와 다음 작업을 이어갈 수 있도록 작성.
> 마지막 업데이트: 2026-05-08

---

## 1. 프로젝트 개요

- **목적**: newtech-platform(아파트/단지 ~34K개 다루는 부동산 플랫폼)에 부동산등기부등본 발급 기능을 추가한다. customer가 등록한 매물에 대해 관리자가 권리검증용으로 등기부등본을 받아본다.
- **외부 API**: [에이픽(apick.app)](https://apick.app/dev_guide/iros1)의 부동산등기부등본 열람/다운로드 API.
  - 가이드 URL: `https://apick.app/dev_guide/iros1` (열람), `https://apick.app/dev_guide/iros_download1` (다운로드)
  - 발급당 비용: **약 780원** (열람 단계에서 과금)
- **이 디렉토리 위치**: `/Users/lmj/00_projects/newtech-platform/etc/등기부등본api/`

---

## 2. 핵심 의사결정 (확정됨)

| 영역 | 결정 | 비고 |
|---|---|---|
| 발급 트리거 | **수동 (관리자 검수 단계)** | customer 매물 등록 시점에 자동 X. 비용 통제 목적 |
| 서비스 형태 | **별도 마이크로서비스** (등기부 API, 가칭 8100 포트) | 메인 백엔드(8000)가 HTTP로 호출 |
| DB | newtech-platform 공유 PostgreSQL **5433에 `registry_request` 테이블 추가** | 별도 스키마 X |
| 메인↔등기부 인증 | `X-Internal-Token` 헤더 | 단순 공유 시크릿 |
| 비용 가드 (보수값) | 20건/일, 10건/시간, 동일매물 24h 중복차단, 같은 부동산 당일 캐시 | `.env`로 조정 가능 |
| 킬 스위치 | `REGISTRY_ENABLED=false`면 모든 요청 즉시 차단 | |

---

## 3. 아키텍처

```
[프론트 5174]                                                
   └ 관리자 검수 페이지                                   
       └→ [메인 백엔드 8000] ─HTTP(X-Internal-Token)─→ [등기부 API 8100] ─→ 에이픽
              ↓                                                   ↓
         매물에 ic_id 저장                              registry_request 테이블 + storage/pdf/
              └────────────────── 공유 PostgreSQL 5433 ──────────────┘
```

발급 흐름:
1. 관리자가 매물 검수 페이지에서 [등기부 발급] 클릭
2. 메인 백엔드가 등기부 API에 `POST /v1/registry/request` (단지 정보 + 동/호 + 매물ID)
3. 등기부 API가 캐시 검사 → miss면 에이픽 호출 → ic_id 받음 → 백그라운드 스레드에서 PDF 폴링/저장
4. 메인 백엔드/프론트가 `GET /v1/registry/{ic_id}` 폴링하여 `status=completed`되면 `pdf_url` 사용

---

## 4. 디렉토리 구조

```
등기부등본api/
├── HANDOFF.md                            # 이 파일
├── .env                                  # 실제 키 (gitignore, APICK_AUTH_KEY 들어있음)
├── .env.example                          # 환경변수 템플릿
├── .gitignore
├── requirements.txt                      # fastapi, httpx, sqlalchemy, psycopg2, pydantic-settings
├── verify_apick.py                       # 단독 검증 스크립트 (DB·서버 없이 1건 발급 테스트)
├── sql/
│   └── 001_create_registry_request.sql   # 테이블 생성 DDL
├── storage/pdf/                          # 발급된 PDF 저장 위치
└── app/
    ├── __init__.py
    ├── main.py        # FastAPI 엔트리, /healthz
    ├── config.py      # pydantic-settings 환경변수
    ├── db.py          # SQLAlchemy 엔진/세션
    ├── models.py      # registry_request ORM
    ├── schemas.py     # Pydantic 요청/응답
    ├── auth.py        # X-Internal-Token 검증
    ├── apick.py       # 에이픽 클라이언트 (열람/다운로드)
    ├── guards.py      # 킬스위치/일·시간 한도/listing 24h 중복차단
    ├── service.py     # 캐시→열람→백그라운드 폴링→PDF 저장
    └── routes.py      # POST /v1/registry/request, GET /{ic_id}, /{ic_id}/pdf, /usage/today
```

---

## 5. 에이픽 API 핵심 사실 (가이드 + 라이브 검증으로 확인됨)

### 5.1 두 단계 호출 패턴
- **열람** `POST /rest/iros/1` — 헤더 `CL_AUTH_KEY` (MD5), FormData `address` 또는 `unique_num` + `type`(토지/집합건물/건물, 기본 집합건물). 응답에 `data.ic_id` 발급.
- **다운로드** `POST /rest/iros_download/1` — FormData `ic_id` + `format`(pdf/excel). 응답 헤더 `result`: 1=성공/2=처리중. 본문은 PDF 바이너리.

### 5.2 라이브 검증으로 확인한 동작 (코드에 반영됨)
1. **비즈니스 실패도 HTTP 401로 응답한다** — body는 정상 JSON. status code로 분기하면 안 되고 JSON 파싱 가능 여부로 분기. (`apick.py`/`verify_apick.py`/`service.py`에 모두 반영)
   - 예: 매칭 실패 응답 `HTTP 401 / {"data": {"error": "검색 결과가 없습니다.", "success": 0}, "api": {"cost": 0, "success": true}}`
   - 매칭 실패 시 **비용 0** (안전)
2. **열람 호출 자체가 ~30초 동기 응답**이다. 끝나면 ic_id 발급 + 다운로드는 거의 즉시(첫 시도) PDF 반환. 폴링 default는 8회×5초로 충분.
3. **단지명이 인터넷등기소 정식 등록명과 정확히 일치해야 매칭됨** — 도로명+동호만으론 매칭 실패. 단지명 표기에 매우 민감.
   - 검증: `덕릉로 780 상계불암대림아파트 103동 102호` → 실패 / `덕릉로 780 동아불암아파트 103동 102호` → 성공
4. 같은 날 동일 부동산 중복 요청 시 당일 최초 발행본이 재열람됨(가이드 명시). 우리는 추가로 `(address_norm, type, issued_date)` UNIQUE로 자체 캐시.

### 5.3 응답 스키마 (실측)
```jsonc
// 열람 성공
{
  "data": {"ic_id": 3767024, "result": 1, "success": 1},
  "api":  {"success": true, "cost": 780, "ms": 29192, "pl_id": 25892570}
}
// 열람 실패 (HTTP 401, body JSON)
{
  "data": {"error": "검색 결과가 없습니다.", "type": "집합건물", "result": 2, "success": 0},
  "api":  {"cost": 0, "success": true, "ms": 1016}
}
```

---

## 6. 검증 이력

| # | 시도 주소 | 결과 | 비용 | 비고 |
|---|---|---|---|---|
| 1 | `서울 노원구 상계동 1289 상계불암대림아파트 103동 102호` | 실패 ("검색 결과 없음") | 0원 | 단지명 추정 오류 |
| 2 | `덕릉로 780 상계불암대림아파트 103동 102호` | 실패 ("검색 결과 없음") | 0원 | 단지명 미정식 |
| 3 | `덕릉로 780 동아불암아파트 103동 102호` | **성공** (ic_id=3767024, 6p PDF, 96.9KB) | 780원 | 정식 단지명 사용 |

**핵심 학습**: 사용자가 처음 알려준 "불암대림"은 별칭/오인이었고 정식명은 "동아불암아파트". 인터넷등기소는 정식 등록명 매칭이 필수.

---

## 7. 엔드포인트 요약 (등기부 API가 노출, 모두 `X-Internal-Token` 필요)

- `POST /v1/registry/request` — 발급 요청. 캐시 hit 시 기존 행 반환, miss면 새 행 + 백그라운드 폴링 시작.
- `GET  /v1/registry/{ic_id}` — 상태 조회 (status: requested/issuing/completed/failed).
- `GET  /v1/registry/{ic_id}/pdf` — PDF 바이너리 (200 또는 202 처리중).
- `GET  /v1/registry/usage/today` — 일일 발급 건수/비용/한도 (모니터링).
- `GET  /healthz` — 헬스체크 (인증 불요).

---

## 8. 실행 방법

```bash
cd /Users/lmj/00_projects/newtech-platform/etc/등기부등본api

# 1) 의존성
pip install -r requirements.txt

# 2) .env 작성 (이미 작성됨 — APICK_AUTH_KEY 들어있음)
#    cp .env.example .env  # 새 환경에서 시작 시

# 3) DB 테이블
psql "<DATABASE_URL>" -f sql/001_create_registry_request.sql

# 4) 단독 검증 (선택, DB 없이 외부 호출만 검증)
python3 verify_apick.py --address "덕릉로 780 동아불암아파트 103동 102호"
#  → ./verify_{ic_id}.pdf 떨어지면 OK
#  → 종료 코드: 0 성공 / 2 키 미설정 / 4 에이픽 실패 / 5 폴링 만료 / 6 PDF 시그니처 비정상

# 5) 서버 실행
uvicorn app.main:app --port 8100 --reload
```

### 메인 백엔드(8000) 통합 호출 예
```python
import httpx
r = httpx.post(
    "http://localhost:8100/v1/registry/request",
    headers={"X-Internal-Token": INTERNAL_TOKEN},
    json={
        "address": "덕릉로 780",                      # 단지 마스터의 도로명 주소
        "dong": "103", "ho": "102",
        "type": "집합건물",
        "requester_id": admin.id,
        "listing_id": listing.id,
    },
    timeout=60,
)
ic_id = r.json()["ic_id"]
# 이후 GET /v1/registry/{ic_id} 폴링 → status=completed → pdf_url 사용
```

---

## 9. TODO — 앞으로 해야 할 일

### P1 (최우선): 단지 마스터에 `iros_official_name` 통합 — 진행중 논의 단계
**왜 필요한가**: 검증으로 확인됐듯 단지명이 인터넷등기소 등록명과 정확히 일치해야 매칭됨. customer가 매번 정식명을 쳐서 입력하는 건 비현실. 단지 마스터에 한 번 매핑해두면 customer는 동/호만 입력해도 됨.

**추천 방식 (A안: 셀프 학습형)**:
```
관리자가 [등기부 발급] 클릭
   ├ 단지에 iros_official_name 있음 → 자동 결합 호출
   └ 비어있음 또는 매칭 실패 → 관리자에게 "정식명을 입력하세요" 폼
                                  └→ 입력 후 즉시 재호출 + 단지 마스터 업데이트
                                     └→ 다음부터 같은 단지는 자동 성공
```
운영 비용 가장 낮음, 매칭 실패는 비용 0이라 안전.

**다른 AI가 이어받을 때 사용자에게 확인할 사항**:
1. newtech-platform 메인 백엔드 코드 위치 (디렉토리)
2. 단지 마스터 테이블/모델 이름과 키 컬럼 (예: `apartments`, `complexes`, `danji` ...)
3. 마이그레이션 방식 (Alembic? raw SQL?)
4. A안(셀프 학습형) 채택할지, 다른 안(B 일괄/C 등록 시 수동/D 외부 데이터)으로 갈지

### P2: 메인 백엔드(8000)에 호출 헬퍼/라우터 추가
- `httpx`로 등기부 API 호출하는 client 클래스
- 매물 모델에 `registry_request_ic_id` 컬럼 (FK 아닌 참조값) 또는 별도 매핑 테이블
- 관리자 검수 페이지용 엔드포인트 노출 (메인 백엔드의 인증 체계 적용)

### P3: 프론트(5174) UI
- 관리자 검수 페이지에 [등기부 발급] 버튼
- 발급 비용/소요시간 안내 모달
- ic_id 받은 후 5초 간격 폴링 → PDF 표시
- iros_official_name 미설정/매칭실패 케이스의 입력 폼 UX (P1과 연동)

### P4: 단지명 표기 변형 자동 시도 (P1의 폴백)
- 매칭 실패 시 "○○아파트", "○○APT", "○○" 등 표기 변형을 자동 1~2회 시도해 학습 비용 절감
- 비용 0이라 안전하지만 인터넷등기소 부담 고려해 횟수 제한

### P5: 통합 테스트
- 실제 에이픽 호출 케이스 (비용 발생) + 모킹 케이스
- 캐시 적중/한도 초과/킬스위치 동작 검증

### P6: 운영 보강
- 일일 사용량 모니터링/알림 (한도 80% 도달 시)
- 검증용 임시 PDF(`verify_*.pdf`) 정리 정책 — 현재 `verify_3767024.pdf` 1건 존재(보관/삭제 미정)
- 백그라운드 다운로드 실패 단지의 자동 재시도 정책

---

## 10. 다른 AI/세션이 알아야 할 주의사항

- **비용 발생 호출은 사용자 동의 필수**. 매칭 실패는 0원 안전, 매칭 성공은 ~780원 자동 과금.
- **`.env`에 실제 에이픽 인증키가 들어있다**. 어떤 형태로도 외부 노출 금지(채팅, 로그, 커밋).
- **`apick.py`는 HTTP status code를 보지 않고 JSON 파싱 가능 여부로 분기한다** (의도적). 에이픽이 비즈니스 실패에 401을 쓰는 비표준 동작 때문. 이 부분 "수정"하면 에러 메시지가 가려진다.
- **단지명 매칭이 실패의 90%다**. 새 단지에서 발급 실패 보고 들어오면 가장 먼저 의심할 것.
- **사용자 메모리에 등록된 사실**:
  - newtech-platform: 포트 8000(백엔드)/5174(프론트), DB 5433 공유, 전국 ~34K 단지, 데이터탐색→단지상세 통합됨
  - 사용자가 "지정 파일만 수정"을 강하게 선호 → 이 디렉토리 외 파일 수정 시 사전 확인 필요
  - "목업 기능 전부 구현 강요 X, 핵심 충분하면 생략하는 판단 먼저 제시" 선호

---

## 11. 빠른 진입 체크리스트 (다른 AI 세션 첫 진입 시)

- [ ] 이 문서 읽기
- [ ] `app/apick.py`, `app/service.py`, `app/routes.py` 한 번씩 훑어보기 (핵심 로직)
- [ ] `verify_apick.py --help`로 검증 스크립트 옵션 파악
- [ ] 사용자에게 P1(단지 마스터 통합) 진행 의사 + newtech-platform 백엔드 위치 확인
- [ ] 비용 발생 호출 전 반드시 사용자 동의 받기
