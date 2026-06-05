# step5 — `registry_db_service` 설계 (등기부 결정적 빌드 + 사내 LLM 요약)

> step4(`internal-migration-registry-spec.md`)에서 확정한 NICE 6테이블 → `PropertyRightsData` 매핑을 **실제 코드로 구현하기 위한 설계**.
> 매핑표·코드열거값·운영주의는 step4가 단일 출처. 본 문서는 중복하지 않고 **서비스 구조·컷오버·파일계획**만 담는다.
> 작성: 2026-06-05, 브랜치 `feat/internal-migration`. 선행: step4 §7-5/§7-7 결정됨, 1번(신청 `rles_unq_no` 컬럼) 구현·반영 완료(`f12c6de`).

---

## 0. 결론 (한 화면)

현행 단일 생산자 `ai_rights_analysis_service.generate_or_get_cached(db, app_id, registry_ic_id) → dict`(PDF→MinerU→gpt-4o)를, **동일 dict 계약**을 반환하는 신설 `registry_db_service.build_rights_data(db, app_id, rles_unq_no)`로 대체한다. 빌드는 **2층**:

- **결정적층 (LLM 무관, 항상 채움)**: 엔트리 3종 + `max_bond_amount`(=SUM 근저당) + `tenant_deposit` + 신선도/카운트. 6테이블 SELECT만.
- **요약층 (사내 LLM)**: `*_summary` 4종 + `comprehensive_opinion`. 입력은 **결정적층 JSON**(OCR markdown 아님) → MinerU·critique 루프 불필요.

데이터 접근은 **A 확정**: 정보계 Oracle → 수집기 ETL → 앱 PG(`kb_estate`)에 6테이블 미러 → 앱 read-only ORM. 호출부는 **source 스위치**(rles_unq_no 있으면 DB경로, 없으면 현 PDF경로) 뒤에 둬 현 흐름 무손상으로 점진 컷오버.

---

## 1. 교체 지점 & 컷오버 전략

**현행 생산자**(`backend/services/ai_rights_analysis_service.py:382`) `generate_or_get_cached` → `dict`. 호출부 2곳:
- `services/analysis_service.py:240` (직접조회/분석 화면 — `gen_rights(db, app_id, ic_id)`)
- `routers/applications.py:114` (신청 등록 직후 백그라운드 prefetch)

**전략**: 생산자를 갈아끼우지 않고 **나란히 두고 디스패처로 선택**한다.

```
get_rights_data(db, app):
    src = _resolve_source(app)              # settings.registry_source + app 값
    if src == "db":   return registry_db_service.build_rights_data(db, app.id, app.rles_unq_no)
    else:             return ai_rights_analysis_service.generate_or_get_cached(db, app.id, app.registry_ic_id)
```

- **피처플래그** `settings.registry_source ∈ {"auto","db","pdf"}` (기본 `"auto"`):
  - `auto` = `rles_unq_no` 있으면 db, 없으면 pdf (전환기).
  - 폐쇄망 런칭 = `"db"` 고정 → PDF 경로(외부 8100/MinerU/외부 LLM) 사용 안 함.
- 두 호출부는 `gen_rights(...)` 대신 `get_rights_data(db, app)`를 호출하도록 한 줄씩 변경.
- **폐쇄망 컷오버 완료 시**: `ai_rights_analysis_service`의 PDF/MinerU 블록(404–486)·`registry_ic_id` 컬럼·8100/8200 설정을 제거(별도 정리 커밋).

## 2. 출력 dict 계약 (동결 — 두 경로 공통)

현 `_empty_result()` 키를 그대로 유지(소비부 `analysis_service.py:246-251`가 의존):

`ownership_entries[]`(name/reg_number/share/address/rank_number) · `ownership_other_entries[]`(rank_number/purpose/receipt_info/details) · `mortgage_entries[]`(rank_number/purpose/receipt_info/main_details/target_owner) · `max_bond_amount`:int · `tenant_deposit`:int · `gap_summary`/`eul_summary`/`seizure_summary`/`priority_summary`/`comprehensive_opinion`:str

**신규 키(additive)**: `inquiry_date`:str(신선도 배지) · `seizure_count`/`prov_seizure_count`/`provisional_disp_count`/`auction_count`/`mortgage_count`:int. → `models/response_models.py:PropertyRightsInfo` + FE `types/loan.ts` + `PropertyRightsInfo.tsx`에 필드 추가(소비는 선택적이라 기존 화면 무손상).

## 3. 결정적층 빌드 (필드별 — 매핑 근거는 step4 §3)

- `mortgage_entries` ← 저당명세 `COLL_I`(현재 유효분). main_details = `PDL_AMT_CTNT`/채무자/근저당권자(`RTP_NM`) 조립.
- **`max_bond_amount` = `SUM(COLL_I.PDL_AMT) WHERE RGTY_PRPS_CD=근저당권설정`**. 질권·전세권·이전·변경 제외. 숫자값 `PDL_AMT`(원단위) 사용, `PDL_AMT_CTNT` 텍스트 파싱 금지. (CASE1 검산 141,000,000)
- `tenant_deposit` = `SUM(COLL_I.PDL_AMT) WHERE 전세권설정`. (미등기 임차=등기부에 없음→불포함)
- `ownership_entries` ← 요약명세 `BRF_I`. `RNNO` **마스킹**(복호 후 가림, ADR-010). 주소는 **표제부 평문 `C11`/`C12`** 사용(소재지/거주지 암호문 회피).
- `ownership_other_entries` ← 상세 `CCRG_D` WHERE `CCRG_DVCD='1'` AND 목적∈{압류,가압류,가처분,경매개시}. 당사자(`PDL_I`) 조인.
- `inquiry_date` ← 기본 `M.IQRY_DT`. counts ← `M.SEIZ_CCNT`/`PRSZ_CCNT`/`PVSL_CCNT`/`AUCT_OPNG_CCNT`/`FXCL_CCNT`.
- **enum/코드는 step4 §2 역산값** — 공통코드 master 확정 전까지 상수맵으로 두고 `# TODO(master)` 없이 한 곳(상수 모듈)에 모아 교체 용이하게.

## 4. 요약층 빌드 (사내 LLM via `LLMClient`)

- `LLMClient`(ADR-008)는 OpenAI 호환 — admin 패널 `LlmConnection` 기본 연결(`base_url`)이 **사내 LLM**을 가리킨다. 라우터/타서비스 직접 SDK 호출 금지, 반드시 `LLMClient` 경유.
- **입력 = 결정적층 결과 JSON**(엔트리+금액). OCR markdown을 안 주므로 환각 원천이 없다 → 현행 `_deterministic_issues`/`_run_critique` 재생성 루프 **불필요**(이식하지 않음).
- 출력: `gap/eul/seizure/priority_summary` + `comprehensive_opinion` 평문(존대형). 시스템 프롬프트는 현 `SYSTEM_PROMPT`의 요약 규칙만 추출해 재사용.
- **폴백 원칙(silent fallback 금지)**: LLM 실패해도 결정적층(엔트리·금액·LTV)은 그대로 반환, 요약 키만 빈 문자열(명시) — 가짜 요약 생성 금지. **핵심 심사 수치는 LLM 가용성과 무관.**
- 캐시: 현 `loan_applications.ai_rights_text` 재사용. **`inquiry_date`를 캐시에 포함**해, 저장된 inquiry_date ≠ 현재 DB inquiry_date면 재빌드(스냅샷 갱신 반영).

## 5. 데이터 접근 — A 확정 (Oracle→PG 미러)

```
정보계 Oracle/DW (NICE 6테이블) ──ETL(수집기 소유)──▶ 앱 PG kb_estate (6테이블 미러) ──read-only──▶ registry_db_service
```

- step1-2 KB 파이프와 **동일 레일**: 적재 주체=수집기(newtech_data), 앱은 read-only(ADR-002 대칭). 앱은 PG 한 곳만 본다(외부 DB 의존 0).
- 앱 측 6테이블은 **read-only ORM 모델**로 미러(기존 `models/complex.py`·`crawl.py` 패턴) — **앱 alembic 마이그레이션 만들지 않음**(수집기 소유 도메인). 신설 `models/registry_nice.py`.
- **적재소유권 ADR 신설 필요**(ADR-011 후보: NICE 6테이블=수집기 소유 read-only). ETL 적재기 자체는 step2 연장선으로 **수집기 레포**에 작성.
- 대가(인지): ETL 지연이 `IQRY_DT` 스냅샷 위에 한 겹 더 → 신선도 배지(§3 `inquiry_date`)로 노출, ETL 주기는 수집기에서 결정.
- B(앱이 Oracle 직접 read)로 전환해도 §3·§4 빌드 로직은 동일, **접속 엔진만 교체**(쿼리 재사용).

## 6. 존재 가드 (1번 이월분)

- `registry_db_service.registry_exists(db, rles_unq_no) -> bool` = 기본 `M` count>0. **복호화 불필요**(행 존재만).
- 배선: 신설 라우터 `GET /api/registry-db/{unq_no}/exists` (trailing slash 없이, `redirect_slashes=False`; `main.py` include). 신청 폼이 부동산고유번호 입력 후 호출 → 없으면 "등기 조회 선행 필요" 안내(미존재라도 입력 자체는 허용; hard block 아님).

## 7. 더미 차단

- `dummy_data.generate_property_rights_info`(random 채권최고액 5~10억)가 매칭 미스 시 무경고 혼입(근거 `docs/dummy-vs-real.md`). DB경로에선 미존재 시 `_empty_result()`(0/빈배열) 반환하고 **더미로 떨어지지 않게** 소비부에서 source=db일 때 더미 폴백 차단.

## 8. 파일 변경 계획 (구현 청사진)

| 파일 | 변경 |
|---|---|
| `backend/services/registry_db_service.py` | **신설** — `build_rights_data`/`registry_exists` + 결정적 빌드 + 요약(LLMClient) |
| `backend/models/registry_nice.py` | **신설** — 6테이블 read-only ORM 미러 (마이그레이션 없음) |
| `backend/routers/registry_db.py` | **신설** — `GET /api/registry-db/{unq_no}/exists`, `main.py` 등록 |
| `backend/services/analysis_service.py` | `:240` `gen_rights` → `get_rights_data(db, app)` 디스패처 호출 |
| `backend/routers/applications.py` | `:114` prefetch 동일 디스패처로 |
| `backend/services/rights_source.py` (또는 analysis_service 내) | **신설** — `get_rights_data` + `settings.registry_source` 스위치 |
| `backend/core/config.py` | `registry_source` 설정 추가(기본 `"auto"`) |
| `backend/models/response_models.py` | `PropertyRightsInfo`에 `inquiry_date`/counts(선택) |
| `frontend/src/types/loan.ts`, `PropertyRightsInfo.tsx` | 신선도 배지·counts 표시(선택) |

## 9. 이 환경에서 가능 범위 / 사내 선결

- **지금 작성 가능**(피처플래그 `pdf` 기본이면 현 동작 무변화): `registry_db_service`/`registry_nice` ORM/디스패처/존재 가드 라우터/설정/요약 프롬프트 — **가정 스키마(step4 §2 역산) 기준**. 단위 빌드 로직·요약은 코드로 완성, 컴파일·기동 검증 가능.
- **사내에서만 검증**: 실 DDL·물리 테이블/컬럼명, 공통코드 master, 복호 모듈/키(주소·RNNO), 6테이블 실접속(ETL 적재 후). → 코드에 시임으로 표시, 실값 들어오면 상수맵/접속만 교체.

## 10. 외부 테스트 픽스처 (사내 반입 전 검증)

사내 정보계 반입 전, **케이스 샘플(`etc/테이블/등기부등본/샘플/`, 로컬 전용·미커밋)을 앱 PG `nice_rles_*` 에 적재**해 `registry_db_service` 를 실데이터로 검증한다.
- 로더1 (xlsx): `backend/scripts/load_nice_samples.py` (개발 한정 — 6테이블 drop+create 후 xlsx 적재, stdlib 파싱). 실행: `DATABASE_URL=...@localhost:5433/kb_estate python scripts/load_nice_samples.py`.
- 로더2 (PDF): `backend/scripts/load_pdf_as_nice.py` — **임의 등기부 PDF → MinerU→LLM 추출(`extract_rights_dict`)→`nice_rles_*` explode** 적재. NICE 샘플 3건 외 어떤 PDF로도 db경로 테스트·브리지. 구조키(NICE_MSGM_NO 등) 합성, 빌더가 쓰는 텍스트 필드만 채움. (컨테이너 실행 권장 — MinerU/LLM 도달.) **사실상 "PDF 업로드→db경로"** — 폐쇄망에서 NICE DB에 없는 물건의 브리지로 승격 가능.
  - 검증(CASE1 PDF): MinerU 10,661자 → LLM → build `max_bond=141,000,000` (xlsx 경로와 수렴). **신선도 실증**: PDF(6/5)는 압류 1건 포함, xlsx DB스냅샷(4/13)은 0건 — step4 §5-1 그대로.
  - 추출 코어는 `ai_rights_analysis_service.extract_rights_dict(db, text, label)` 로 분리(ic_id 경로와 공유, 실패·빈 추출은 캐시 안 함).
- **검증 결과(2026-06-05)**: CASE1 `max_bond_amount=141,000,000`(근저당 66M+75M, 질권 60M 제외) ✓ PDF 검산 일치 · CASE2 75,600,000(소유권외 12건) · CASE3 1,623,600,000. 소유자/지분/도로명주소/실명번호 마스킹 정상.
- **이 테스트가 잡은 골격 스키마 교정**(실 명세 대조): ① 자식 테이블은 `NICE_MSGM_NO`(전문관리번호, 샘플 10자리)+`RLES_UNQ_NO` 복합키 → **최신 스냅샷(기본행 IQRY_DT 최대)의 MSGM 으로 조인**(단일 rles_unq_no 필터는 다중조회 오염) ② 상세(CCRG_D)는 `CCRG_RANK_NO`(RGTY_RANK_NO 아님)·`RGTY_PRPS_CD` 없음 ③ 표제부 `HDR_CTNT` 는 명세상 NUMBER 이나 실제 텍스트(주소·호·면적) ④ 주소는 표제부 `C12` 도로명/`C11` 지번 평문(소재지 `LCTN_ADDR` 는 base64 암호문) ⑤ `NICE_MSGM_NO` 길이 명세 14 vs 샘플 10 드리프트.
- 남은 관찰: CASE2 는 표제부 샘플이 비어 주소 빈값(샘플 특성). 필요 시 `LND_LCTN_ADDR` 폴백 검토.

## 11. 다음 단계

1. ~~ADR-011~~ ✅ · ~~골격 구현~~ ✅ · ~~외부 테스트 픽스처+검증~~ ✅ (2026-06-05).
2. (인레포) FE 신선도 배지(`inquiry_date`) + 존재가드 폼 배선(`/api/registry-db/{unq}/exists`).
3. 수집기 레포에 6테이블 ETL(step2 연장).
4. 사내 실 DDL/master/복호 확정 후 상수·접속 교체 → `registry_source=db` 운영 검증.
