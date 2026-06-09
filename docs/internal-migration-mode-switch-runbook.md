# 사내 데이터 이관 — dev ↔ prod 모드 전환 런북

> **이 문서의 목적**: 나중에 상황을 잊은 상태에서도 "외부 테스트(dev)"와 "폐쇄망 운영(prod)"
> 사이를 안전하게 전환·검증할 수 있게 하는 **운영 절차서**. 설계 근거는 아래 단일 출처를 인용한다.
>
> - 아키텍처 결정: `docs/architecture-decisions.md` (ADR-002 수집기 소유 read-only / ADR-011 등기부 6테이블)
> - KB 매핑·갭: `docs/internal-migration-field-mappings.md` (step1)
> - KB ETL 사양(수집기): `docs/internal-migration-etl-spec.md` (step2)
> - 등기부 DB 서비스: `docs/internal-migration-registry-db-service-design.md` (step5)
> - 좌표/지오코딩: `docs/internal-migration-geocoding-strategy.md` (step3)
> - 세션 진입점: `docs/internal-migration-handoff.md`

---

## 1. 한 장 요약 (멘탈 모델)

서비스는 **두 종류의 데이터**를 읽는다: KB 시세(단지/평형/시세/실거래)와 등기부 권리.
이관의 핵심은 **"내부망과 동일한 형태의 DB(내부형식)"를 계약면(seam)으로 고정**하고,
그 DB를 **누가 채우는지(feeder)만 모드별로 바꾸는** 것이다. 읽기경로는 모드와 무관하게 동일.

```
  [dev feeder]  크롤/PDF ─정형화→ ┐                                    ┌→ 서비스 화면
                                  ├─ 내부형식 DB (계약면, 모드 불변) ──┤   (읽기경로 고정)
  [prod feeder] Oracle ─수집기ETL→ ┘                                    └→
```

**모드 = feeder 선택일 뿐.** 그래서 `.env` 두 줄로 전환된다(§3).

### 1.1 두 도메인은 계약면 위치가 다르다 (중요 — 잊지 말 것)

| 도메인 | 앱이 읽는 곳 | "내부형식 DB"의 실체 | 이유 |
|---|---|---|---|
| **KB 시세** | app-schema (`complexes`/`areas`/`kb_prices`/`transactions`) | `CCTR_*` 6테이블 → **그 위에서 app-schema로 변환 적재** | 기존 app-schema 읽기경로가 45,936단지·197만시세에서 이미 검증됨 → 보존(저위험). = **Architecture A** |
| **등기부** | 내부형식 `nice_rles_*` 6테이블 **직접** | `nice_rles_*` 자체 | 기존 등기부 경로(외부API→PDF→LLM)가 폐쇄망에서 깨짐 → 내부형식 직접 읽기로 대체 |

즉 **KB는 `CCTR_*`를 거쳐 app-schema로 변환**(앱은 `CCTR_*`를 직접 읽지 않음),
**등기부는 `nice_rles_*`를 직접** 읽는다. 이 비대칭이 A 선택의 결과다. 전환 시 양쪽을
따로 챙겨야 한다.

---

## 2. 상황 매트릭스 (지금 어디에 있나)

| 상황 | `DATA_MODE` | `REGISTRY_SOURCE` | KB 데이터 출처 | 등기부 출처 |
|---|---|---|---|---|
| **A. 현행 외부 운영** (코드 기본값) | `dev` | `pdf` | 크롤 → app-schema (그대로) | 외부 8100 API → MinerU → LLM |
| **B. 외부 내부형식 테스트** | `dev` | `auto` | 크롤 → `CCTR_*` → app-schema (검증) | `nice_rles_*`(로더 적재), 미적재 물건은 PDF 폴백 |
| **C. 폐쇄망 운영** | `prod` | `db` | Oracle → `CCTR_*` → app-schema (수집기) | `nice_rles_*`(수집기 Oracle 미러) |

- **두 노브**: `DATA_MODE`(dev/prod, KB feeder 맥락 + 개발 스크립트 차단) / `REGISTRY_SOURCE`(등기부 읽기경로).
- `DATA_MODE` 기본값은 **`dev`** — 앱 런타임 읽기경로를 바꾸지 않으므로 현행 동작 무변화. 운영 전환 시 `prod`로.
- `REGISTRY_SOURCE` 기본값은 **`pdf`** — 현행 동작 보존. 내부형식 검증/운영 시 `auto`→`db`.

---

## 3. 전환 = `.env` 블록 교체

### dev (외부 테스트)
```dotenv
# backend/.env
DATA_MODE=dev
REGISTRY_SOURCE=auto        # rles_unq_no 있으면 nice_rles_*(db), 없으면 PDF 폴백
# Oracle 설정 불필요
```

### prod (폐쇄망)
```dotenv
# backend/.env
ENVIRONMENT=production
DATA_MODE=prod
REGISTRY_SOURCE=db          # 폐쇄망은 외부 PDF API 불가 → 항상 내부 6테이블
JWT_SECRET_KEY=<운영 시크릿>  # assert_production_safe() 가 기본값이면 기동 거부
DATABASE_URL=postgresql://<운영 PG>
CORS_ORIGINS=https://<운영 도메인>
```
```dotenv
# 수집기(newtech_data) 쪽 .env — Oracle 원천 (step2 사양)
ORACLE_DSN=<host:port/service>
ORACLE_USER=<...>
ORACLE_PASSWORD=<...>
ORACLE_ETL_BATCH_SIZE=5000
```

`prod`로 두면 개발 적재 스크립트(`build_cctr_from_crawl`, `cctr_to_app --apply`,
`load_nice_*`)는 **스스로 거부**한다(폐쇄망에서 실수로 테이블을 덮어쓰는 사고 차단).

---

## 4. dev 모드 — 외부에서 내부형식으로 테스트하기

목적: Oracle 없이, 크롤/PDF 데이터를 내부형식으로 정형화해 **운영에서 쓸 변환·읽기경로를 미리 검증**.

### 4.1 KB: 크롤 → `CCTR_*` → app-schema 라운드트립

```bash
# (1) 크롤 app-schema → 내부형식 CCTR_* 정형화 (개발용 테이블 재생성)
docker compose exec backend python scripts/build_cctr_from_crawl.py --limit 300
#   --limit 0 = 전체(무겁다). 테스트는 수백 단지로 충분.

# (2) CCTR_* → app-schema 변환을 기존 데이터와 대조 (쓰기 없음/비파괴)
docker compose exec backend python scripts/cctr_to_app.py --verify
#   verify/apply 는 (1)이 적재한 CCTR_* 범위만 본다. --limit 0 으로 전량 빌드 후 verify 하면 메모리 큼.

# (3) 빈/별도 app-schema에 실제 적재해 보려면 (dev 전용, 클린룸에서만)
docker compose exec backend python scripts/cctr_to_app.py --apply
```

**검증 기준선 (정상 결과 예시, --limit 300)**:
```
build:  cctr_kb_apt_m 300 · _pntp_i 1560 · _qtn_l 36148 · txcs_hist 26292 · stdng_c 18 · mpng_b 300
verify: complexes 핵심일치=300 핵심불일치=0 · region_code 교정=89
        kb_prices 일치=36148 불일치=0 app에없음=0
        areas app매칭=1560/1560 · txcs_hist KBA해소=26292/26292
```
- `핵심불일치=0` 이면 변환(금액 만원→원, 날짜, 주소조합, 평형/시세 조인)이 충실. 가격경로(LTV/공정가) 무결.
- `region_code 교정`은 **정상**(§7-1). `--apply`는 라이브 app-schema(45k)를 변형하므로 클린룸 외 실행 금지 — `--verify`로 충분.

### 4.2 등기부: 샘플/PDF → `nice_rles_*`

```bash
# 케이스 샘플(xlsx 6테이블) 적재 — 샘플 xlsx 는 미커밋 로컬(etc/테이블/등기부등본/샘플)에만
# 있어 컨테이너에 마운트 안 됨 → 호스트 venv 로 실행(아래만 예외, 나머지는 compose exec).
DATABASE_URL=postgresql://kb_user:<pw>@localhost:5433/kb_estate \
  backend/.venv/bin/python backend/scripts/load_nice_samples.py

# 임의 등기부 PDF → 6테이블 재구성(컨테이너 — MinerU·LLM 도달)
docker compose cp <pdf> backend:/tmp/r.pdf
docker compose exec backend python scripts/load_pdf_as_nice.py /tmp/r.pdf <부동산고유번호14자리>
```
적재 후 `REGISTRY_SOURCE=auto`로 두면 신청의 `rles_unq_no`가 적재돼 있으면 `nice_rles_*`를,
없으면 기존 PDF 경로로 폴백한다. 결정적 빌드+LTV 검증은 step5 문서 참조.

신청폼 ②의 **부동산고유번호 검색·조회**(주소→고유번호 후보, 결정적 요약 미리보기)도
`REGISTRY_SOURCE=auto|db`에서만 동작한다(pdf면 503). 검색 출처는 적재된 `nice_rles_*`뿐 —
사내 심사시스템 고유번호 검색은 앱 호출 불가라, 향후 사내 디렉토리가 열리면
`registry_db_service.search_registries`만 교체하면 된다.

---

## 5. prod 모드 — 폐쇄망 운영

앱 코드는 dev와 **동일**하다. 달라지는 것은 (1) `.env`(§3), (2) **내부형식 DB를 채우는 주체 = Oracle ETL**.

### 5.0 구현된 #1 운영 ETL (Oracle → PG 내부형식 미러) — **DSN만 교체** ✅
`scripts/oracle_to_pg_etl.py` 가 정보계 Oracle `CCTR_*`(6) + `CUWT_NIC_RLES_*`(6) 을 PG 내부형식
(`cctr_*`/`nice_rles_*`)으로 **전체 미러**한다. 앱은 `INTERNAL_ONLY=true` 로 그 미러를 읽음
(시세=`internal_market_service`, 등기부=`registry_db_service`).

- **운영 전환 = `.env` 의 `ORACLE_DSN`/`ORACLE_USER`/`ORACLE_PASSWORD` 3줄만 사내 정보계로 교체** → 같은 ETL 실행.
- 물리 테이블/컬럼명이 사내와 다르면 `scripts/internal_oracle_common.py` 의 `TABLE_MAP`·컬럼만 조정(ETL 본체 불변).
- 단위: PG 미러는 Oracle 원본 그대로(만원). 읽기 시 ×10000. 현재 전체 재적재(테이블별 delete→insert),
  대용량 운영은 워터마크 증분(step2 §2)이 후속.

**Oracle 없이 #1 검증(dev 시뮬레이터)**:
```bash
docker compose --profile oracle up -d oracle                    # 로컬 Oracle(gvenzl/oracle-free, 기본 stack 비포함)
docker compose exec backend python scripts/oracle_sim_setup.py  # 12테이블 생성 + 현 PG데이터 시드(정보계 흉내, dev전용)
docker compose exec backend python scripts/oracle_to_pg_etl.py  # Oracle→PG 미러 (= 운영과 동일 코드)
```
검증됨: 시뮬레이터→ETL→PG 65,957행, 앱이 Oracle 경유 데이터로 시세(24억)·등기부(6.35억) 산출.

> 참고: 아래 §5.1/§5.2는 원래 step2 안(Oracle→app-schema 변환 적재, Architecture A). 실제 구현은 **§5.0(미러+INTERNAL_ONLY 직접읽기)** 로 수렴 — 운영 app-schema가 어차피 ETL-only라 두 방식 결과는 동치.

### 5.1 KB: Oracle `CCTR_*` → app-schema (수집기, step2 — 대안)
- 수집기(newtech_data)가 Oracle `CCTR_*` 6테이블을 읽어 **§4.1과 동일한 변환 매핑**으로
  app-schema(`complexes`/`areas`/`kb_prices`/`transactions`)에 멱등 적재. ADR-002상 적재 주체는 수집기.
- 변환 규칙의 단일 출처는 `cctr_to_app.py`의 `complex_fields/area_fields/price_fields`와
  step1 field_mappings. 수집기 구현이 이와 **단위 동치**를 유지해야 한다(원/만원 드리프트 = LTV 붕괴).
- dev의 PG `CCTR_*`는 **Oracle을 시뮬레이션한 것**. prod에선 PG에 `CCTR_*`를 두지 않고 Oracle을 직접 읽는다(또는 미러). 컬럼명·형태는 `models/internal_kb.py`가 청사진.

### 5.2 등기부: Oracle `CUWT_NIC_*` → `nice_rles_*` (수집기 미러)
- 수집기가 정보계 Oracle `CUWT_NIC_RLES_*` 6테이블을 앱 PG `nice_rles_*`로 미러 적재.
- 앱은 `REGISTRY_SOURCE=db`로 `nice_rles_*`를 직접 읽어 결정적 빌드(권리/근저당/신선도) + 사내 LLM 요약.

---

## 6. 전환 체크리스트

### dev → prod (운영 전환 시)
사전 조건(모두 충족 후 `.env` 교체):
- [ ] **Oracle 물리 테이블명·컬럼명 확정** — `CCTR_*`/`CUWT_NIC_*` 실 DDL probe. 추측 금지(step2 §9).
      `models/internal_kb.py`의 ★표시 컬럼(STDNG_C 동명 등)은 실 DDL로 검증.
- [ ] **oracledb 드라이버** — **수집기(newtech_data)** 에 설치(Architecture A에서 앱은 Oracle 직결 안 함). `SELECT 1 FROM DUAL` 헬스체크.
- [ ] **수집기 ETL** 구현·검증: Oracle→app-schema(KB), Oracle→`nice_rles_*`(등기부). step2 §8 도입 단계.
- [ ] **등기부 복호 모듈 + 공통코드 master** (주소/실명번호 암호문, 등기목적코드) 반입.
- [ ] **지오코딩** 결정(행안부 내비DB + 건물관리번호 조인, step3) — 미적용 시 지도/인근동향만 제한, 적재 무결성 OK.
- [ ] **운영 시크릿**: `JWT_SECRET_KEY`/`DATABASE_URL`/`CORS_ORIGINS` 기본값 제거(미설정 시 `assert_production_safe()` 기동 거부).

전환:
- [ ] `backend/.env`: `DATA_MODE=prod`, `REGISTRY_SOURCE=db`, `ENVIRONMENT=production` (§3).
- [ ] 수집기 `.env`: Oracle 접속.
- [ ] backend 재기동.

전환 후 검증:
- [ ] `GET /api/admin/migration/checklist` (ADMIN) — `data_source_mode`(운영인데 dev/pdf면 자동 빨간불)·`app_migration` 확인.
      ⚠️ `db_connections`/`mappings`/`oracle_driver` 항목은 **앱이 Oracle에 직접 붙던 구 어댑터(DataSourceMapping)** 용이라
      Architecture A의 게이트가 **아니다**(A에선 앱이 app-schema·`nice_rles_*`만 읽고 Oracle 접속은 수집기 몫). 이 3개는 무시하고 아래 실측으로 판정.
- [ ] **(실측 게이트)** 분석 화면이 더미 폴백 아닌 실데이터로 렌더(KB), 등기부 권리분석이 `nice_rles_*` 결정적 빌드로 산출.
- [ ] **(실측 게이트)** 표본 신청 1건의 LTV/근저당 합계를 사내 원천과 대조.

### prod → dev (롤백 / 외부 복귀)
- [ ] `backend/.env`: `DATA_MODE=dev`, `REGISTRY_SOURCE=auto`(또는 `pdf`로 완전 현행 복귀).
- [ ] backend 재기동. KB는 크롤 app-schema, 등기부는 PDF/로더 경로로 즉시 복귀(코드 변경 없음).

---

## 7. 알려진 변환 차이 · 데이터 품질 (전환 전 인지)

1. **region_code 교정 (약 18%, 라이브 풀셋·시점 변동)**: 내부형식은 `region_code = 법정동코드[:5]`로
   derive. 크롤 시절 `region_code`는 별도 출처라 dong_code와 어긋나는 단지가 있다(검증된 값은
   --limit 300 라운드트립의 교정 89건). 운영엔 derive만 존재 → **derive가 정답**, "교정"은 정상.
   (지역검색 매칭이 dong_code 기준으로 통일됨)
2. **built_year 포맷**: 크롤 `'1984.06'` ↔ 내부 `CMCN_YM='198406'`. 앱은 `[:4]`로 연도 파싱하므로
   로직 동일, 저장 문자열만 표기차(무해).
3. **pyeong**: 크롤은 종종 NULL. 내부형식 적재 시 `㎡/3.305785`로 파생 → 오히려 채워짐.
4. **금액 단위**: 내부형식 만원 ↔ app-schema 원. 변환 `×10000` 필수(미적용 시 LTV 붕괴). KB시세·실거래 모두 만원 정렬이라 라운드트립 무손실.
5. **호가(listing)**: 원천 미수집 → 보류(빈 상태). JB 가중 `W_NAVER=0`이라 LTV/공정가 무영향.
6. **위경도**: Oracle에 없음 → 지오코딩(step3) 전까지 NULL. 지도/인근동향/입지(facility)만 제한, 적재 무결성 지장 없음.
7. **실거래↔단지 매칭**: KBA 채워진 행은 직접 조인, 공백행은 크로스워크(`CCTR_KB_APT_TXCS_MPNG_B`)→이름매칭. 미매칭은 skip(표본 축소).

---

## 8. 파일·스크립트 레퍼런스

| 파일 | 역할 | 모드 |
|---|---|---|
| `backend/models/internal_kb.py` | KB 내부형식 `CCTR_*` 6테이블 ORM (Oracle 동형 청사진) | 공통(dev=PG 미러, prod=Oracle 형태) |
| `backend/scripts/build_cctr_from_crawl.py` | 크롤 app-schema → `CCTR_*` 정형화 | dev 전용 |
| `backend/scripts/cctr_to_app.py` | `CCTR_*` → app-schema 변환(`--verify`/`--apply`). **변환 매핑의 단일 출처** | dev 실행(prod은 수집기가 동일 매핑 구현) |
| `backend/models/registry_nice.py` | 등기부 내부형식 `nice_rles_*` 6테이블 ORM | 공통 |
| `backend/scripts/load_nice_samples.py` | 등기부 케이스 샘플(xlsx) → `nice_rles_*` | dev 전용 |
| `backend/scripts/load_pdf_as_nice.py` | 등기부 PDF → `nice_rles_*` 재구성 | dev 전용 |
| `backend/services/registry_db_service.py` | `nice_rles_*` 결정적 권리 빌드 + LTV + 사내 LLM 요약 | 공통(db경로) |
| `backend/services/rights_source.py` | `REGISTRY_SOURCE`로 db/pdf 경로 디스패치 | 공통 |
| `backend/core/config.py` | `data_mode`, `registry_source` 설정 | 공통 |
| `GET /api/admin/migration/checklist` | 운영 전환 사전조건 자동 점검(ADMIN) | 공통 |

**ADR-002/011**: `CCTR_*`·`nice_rles_*`·app-schema 수집기 테이블은 모두 수집기 소유 read-only.
앱은 alembic 마이그레이션을 만들지 않는다(`alembic/env.py` 제외 목록). 개발 적재 스크립트만
예외적으로 dev에서 이 테이블을 쓰며, `DATA_MODE=prod`에서 자가 차단된다.
