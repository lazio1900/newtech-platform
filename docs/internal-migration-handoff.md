# 사내 데이터 이관 — 작업 핸드오프 (다음 세션/AI 진입점)

> 이 문서는 **오케스트레이션용 인덱스**다. 세부 사양은 중복 기재하지 않고 step1/step2 문서로 링크한다.
> 결정·근거의 단일 출처: 본 문서 §관련 문서 표. 충돌 시 그 원본 문서가 우선.
> 최종 갱신: 2026-06-04 (브랜치 `feat/internal-migration`, HEAD `3358efa`).

---

## 0. 한 화면 요약

**무엇을:** `newtech-platform`(이미 완성된 JB우리캐피탈 질권담보 대출심사 웹서비스)의 **조회 경로를, 사내 Oracle(스키마 `17.기준관리`)에 이미 쌓이고 있는 실데이터에 연결**하는 작업.

**아닌 것:** 외부에서 수집한 데이터를 일회성으로 반입(import)하는 ETL 마이그레이션이 **아니다**. 이미 사내에 존재·축적 중인 데이터 위에서 기존 서비스를 돌리는 것이 목표. (이 구분을 사용자가 두 번 명시적으로 정정했다 — 헷갈리지 말 것.)

**왜 ETL이 결국 필요한가:** 앱은 수집기 소유 테이블을 read-only 로만 읽는다(ADR-002). 그래서 Oracle 원천을 앱이 직접 읽지 않고, **수집기(newtech_data)가 Oracle→`kb_estate`(공유 PostgreSQL)로 업서트**하면 앱은 기존처럼 `kb_estate`를 read-only 로 읽는다. = 읽기쓰루가 아니라 수집기 쪽 ETL 동기화.

**진행 상태:** step1(매핑) ✅ · step2(ETL 사양) ✅ · **step3(좌표/지오코딩 전략) ❌ 미완** → 여기가 다음 작업.

---

## 1. 지금 어디까지 했나 (산출물 위치)

| | 산출물 | 위치 | 커밋 |
|---|---|---|---|
| step1 | field_mappings 초안 + 로더 갭 표 | `docs/internal-migration-field-mappings.md` | `065f3b6` |
| step2 | Oracle→kb_estate ETL 적재기 사양(수집기 신설) | `docs/internal-migration-etl-spec.md` | `3358efa` |
| step3 | 좌표/지오코딩 전략 | **아직 없음** (`docs/internal-migration-geocoding-strategy.md` 미생성) | — |
| 분석 메모리 | 6테이블→5엔티티 판정 요약 | `~/.claude/.../memory/project_internal_kb_migration.md` | (메모리) |

- **브랜치**: `feat/internal-migration`. 신규 이관 코드는 전부 이 브랜치에서.
- **복원점 태그**: `pre-internal-migration` = 커밋 `ba0e0bd`("…신규개발 전 현재버전 체크포인트"). 롤백 필요 시 이 태그로.
- **커밋 안 한 것(의도적)**: `etc/등기부등본api/logs/uvicorn.out`(로그), `etc/테이블/`(명세·샘플 xlsx — **실주소·실거래가 포함이라 GitHub 노출 회피, 로컬 보관만**). git status 에 항상 떠 있는 정상 상태다.

---

## 2. 시스템 구도 (필독 — 이거 모르면 잘못 짠다)

| | newtech-platform (이 레포) | newtech_data / kb-estate-collector |
|---|---|---|
| 경로 | `/Users/lmj/00_projects/newtech-platform` | `/Users/lmj/00_projects/newtech_data/kb-estate-collector` |
| 역할 | 심사 웹서비스, 데이터 **read-only 소비자** | KB수집·**데이터 writer**, Celery |
| 포트 | FastAPI 8002 + Front 5173 | FastAPI 8000 + Front 5174 |
| ETL 책임 | ❌ (앱은 쓰기 금지) | ✅ **Oracle→kb_estate 적재기가 여기 신설됨** |

- 공유 인프라: PostgreSQL `5433` / DB `kb_estate` / user `kb_user`, Redis `6379` (본 레포 compose 가 띄움).
- **ADR-002**: `complexes/areas/kb_prices/transactions/listings/crawl_*/raw_payloads` 는 수집기 소유. 앱은 read-only, 앱에서 이 테이블에 마이그레이션·INSERT/UPDATE 금지. → **그래서 Oracle 적재 코드는 platform 이 아니라 collector 레포에 작성한다.**
- Alembic 분리: 앱 `alembic_version_app` / 수집기 `alembic_version`. 같은 DB 공존. ETL용 신규 테이블(`etl_watermarks`, areas UNIQUE)은 **수집기 alembic**에서.

---

## 3. 원천 ↔ 앱 엔티티 (요약 — 상세는 step1 문서)

사내 Oracle 6테이블(스키마 `17.기준관리`) → 앱 표준 5엔티티. 자연키 `KB_QTN_RLES_GD_CD` = `'KBA######'`(9자).

| Oracle 테이블 | → 앱 엔티티 | 비고 |
|---|---|---|
| `CCTR_KB_APT_M` | complex(단지) | 주소조각 6컬럼·`KB_QTN_STDNG_CD`(10자 법정동)·`CMCN_YM`(준공 YYYYMM)·`TOT_GEN_CNT`. **lat/lng 없음** |
| `CCTR_KB_APT_PNTP_I` | area(평형) | `(KBA, PNTP_SEQNO)` 복합. `EXUSE_ARE`(전용㎡)/`PNTP_ARE`(공급㎡) |
| `CCTR_KB_APT_QTN_L` | kb_price(KB시세) | `IVST_BASE_DT`·`DEAL_GNRL_TXCS`(일반=중심)/`DEAL_MXPR`(상한)/`DEAL_MNPR`(하한), **단위 만원** |
| `CCTR_APT_TXCS_HIST` | transaction(국토부 실거래) | `SEQNO`·`TX_DT`·`TX_AMT`(만원)·`APT_ARE`·`RLVN_FLR`. `is_cancelled` 컬럼 없음. **`DW_LDNG_DTTM` 없음**(워터마크는 `LAST_PROCS_DT`+`TIME`) |
| `CCTR_KB_APT_STDNG_C` | (참조) 법정동코드 마스터 | |
| `CCTR_KB_APT_TXCS_MPNG_B` | (참조) 크로스워크 | 실거래↔KB **이름 매핑**(`APT_NM`↔`KBA`). 실거래에 KBA 공백인 행 보강용 |

**커버리지 판정** (워크플로 적대적 검증 완료):
- 🟢 **대체 가능**: 단지검색 · 평형별 KB시세 · 공정가/LTV — 더미→실데이터 전환 가능.
- 🔴 **막힘**: 인근동향 · 지도 · 입지(facility) — **위경도 전무** → 주소→좌표 지오코딩 백필 선행 필요(= step3).
- 🔴 **보류**: 호가(listing) — 원천 테이블 없음. **화면은 유지(빈 상태)**. JB 가중치 `W_NAVER=0`이라 LTV/공정가 무영향. (사용자 지시: 호가 화면 남겨둘 것.)
- 🟡 **degraded**: 실거래↔단지 매칭 — KB코드 부분채움이라 이름기반 부분매칭, 미매칭은 누락.

**필수 변환(놓치면 사고)**: 금액 **만원→원 ×10000**(미변환 시 LTV 붕괴) · `is_cancelled=False` 강제(NULL이면 전 거래 누락) · KBA문자열 보존(`kb_complex_id`/`kb_area_code`) + surrogate int PK · `region_code = 법정동코드[:5]` · KB시세↔평형은 `PNTP_SEQNO` 로 정확 조인. (현업 확정: **"평균가"=일반가=`DEAL_GNRL_TXCS`→`general_price`**, 상/하한은 high/low 슬롯.)

---

## 4. 다음 작업 = step3 (좌표/지오코딩 전략)

**목표**: Oracle 에 lat/lng 가 없어 막힌 인근동향/지도/입지를, 주소 기반 지오코딩으로 활성화할지·어떻게 할지 결정.

**핵심 결정 드라이버 (사용자만 답할 수 있음)**: 금융사 **사내 폐쇄망에서 외부 지오코딩 API(카카오/네이버/VWorld 등) 호출이 가능한가?** 여기서 갈린다 —
- 호출 가능 → 외부 지오코더 배치(`geocode_complexes_task`) 신설.
- 불가(폐쇄망) → 오프라인 지오코딩(좌표 사전 DB·법정동 중심좌표 근사) 또는 사내에 좌표 원천 확보 협의.

**설계 골격(step2 §7 에 분리해 둠)**: 적재 시 lat/lng=`None`(nullable이라 무결성 지장 없음) → 별도 `geocode_complexes_task`(`WHERE lat IS NULL AND address IS NOT NULL`, `road_address` 우선) 배치. 기존 수집기 좌표 출처는 KB detail API라 Oracle엔 적용 불가.

**⚠️ 이력 주의**: 직전 세션에서 step3 를 웹리서치 워크플로(`wai3o60mz`)로 돌렸다가 **실패**했다 — 웹리서치 서브에이전트들이 `StructuredOutput` 을 안 부르고 종료. 재시도 시 (a) 스키마를 단순화하거나 (b) 웹검색과 구조화출력 단계를 분리하거나 (c) "부분/저신뢰여도 무조건 StructuredOutput 호출" 지시를 명확히. 또는 폐쇄망 여부를 **먼저 사용자에게 묻고** 답에 맞는 가지만 조사하면 리서치 범위가 절반으로 준다(추천).

**산출 형식**: `docs/internal-migration-geocoding-strategy.md` 작성 → 사용자 스타일로 커밋 → 운영 결정사항(폐쇄망 여부 등)은 대화로 제시.

---

## 5. step3 이후 (구현 단계 — 아직 착수 전)

step2 사양대로 **수집기(newtech_data)** 에 ETL 구현:
- `src/connectors/oracle_internal.py` (fetch/parse만, `oracledb` thin) — **수집기에 `oracledb>=2.0.0` 부재 → requirements 추가 필수**.
- `src/workers/tasks.py` 에 `ingest_oracle_masters/prices/transactions_task` (FK resolve·M1/M2 룩업맵·2단계 실거래 매칭·skip+quarantine·멱등 on_conflict). 청사진 = 기존 `molit_transaction` 태스크.
- `src/core/config.py` Oracle DSN, `EtlWatermark` 모델+마이그레이션, `etl` Celery 큐(KB 큐와 격리), beat 1엔트리.
- 검증 단계는 step2 §8 참조.

---

## 6. 선결 확인 / 미해결 (실 Oracle 접근·현업 승인 필요 — 이 환경에선 검증 불가)

step2 §9 의 open questions. 추측 금지, probe/DESCRIBE 로 실제 확인할 것:
- **물리 테이블명·컬럼명 확정**(`CCTR_*` 및 KBA/`PNTP_SEQNO`/`IVST_BASE_DT`/`TX_DT`/`SEQNO`/`DW_LDNG_DTTM` 은 명세·샘플 기반 추정).
- **워터마크 NOT NULL·단조증가** 여부(KB계열 `DW_LDNG_DTTM`, 실거래 `LAST_PROCS_DT`) → 증분 안정성.
- **`floor`(RLVN_FLR) NULL 빈도** → `idx_transaction_unique` 멱등 깨짐(PG에서 NULL≠NULL) → 대체값 정규화 결정.
- **areas `(complex_id, kb_area_code)` UNIQUE 신설 승인**(수집기 소유 스키마 변경) — on_conflict 멱등 확보용.
- **스키마 드리프트(별건)**: `kb_prices.price`/`general_price` 가 초기 마이그레이션에서 `Integer`로 생성됨(모델은 `BigInteger`). 원(만원→원) 적재 시 `Integer` 상한 오버플로 위험 → 확인.
- crosswalk 1:N 충돌 우선순위, run/task 추적(CrawlRun/CrawlTask) ETL 적용 여부.
- **지오코딩 제공자·API키·쿼터 + 폐쇄망 외부호출 가능 여부**(= step3 의 결정 드라이버).

---

## 7. 작업 규칙 (이 사용자/레포에서 반드시)

- **커밋·푸시는 명시 지시("커밋해"/"푸시해")가 있을 때만.** 작업 끝났다고 자동 커밋 금지.
- **커밋 메시지 스타일**(사용자 패턴 유지 — 본인이 나중에 알아보게): 한 줄 한국어
  `commit 2026-06-04 : 사내 이관 stepN — 무엇을·왜`
  + `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` 트레일러.
- **`git add .`/`-A` 금지**, 파일 단위 add. `etc/테이블/`·로그·`.env`·시크릿 staging 절대 금지.
- **푸시 경로**: 이 맥에 `gh` CLI 인증됨(account `lazio1900`). 비대화형 세션에서 `git push` 직접 가능. (`osxkeychain` 헬퍼는 비대화형서 실패하니 의존 금지 — gh 토큰 헬퍼만 동작. 메모리 `reference-github-push-auth` 참조.)
- platform 쪽에서 수집기 소유 테이블 건드리지 말 것(ADR-002). `backend/_to_extract/` 수정·삭제 금지(ADR-003).

## 관련 문서 (단일 출처)

| 주제 | 문서 |
|---|---|
| 매핑 정의·로더 갭 | `docs/internal-migration-field-mappings.md` (step1) |
| ETL 적재기 사양 | `docs/internal-migration-etl-spec.md` (step2) |
| 아키텍처 결정 | `docs/architecture-decisions.md` (ADR-001~010, 특히 002/003) |
| 더미 vs 실데이터 화면별 | `docs/dummy-vs-real.md` |
| 연동·포트·DB 소유권 | `INTEGRATION.md` |
| 레포 규칙 | `CLAUDE.md` |
