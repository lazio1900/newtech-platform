# 사내 데이터 이관 — 등기부등본(NICE) DB 통합 사양 (step 4)

> 입력: 사용자 제공 `etc/테이블/등기부등본/` (명세 6 + 샘플 3케이스×6 + 원본 PDF 3). 2026-06-05.
> 검증: 6개 명세 컬럼 전수 + 3케이스 샘플 실측 + 원본 등기사항전부증명서 PDF 대조(CASE1 6쪽 전수) + 플랫폼 권리분석/LTV 코드 경로 매핑. critical 가설(저당명세=현재유효권리, 신선도)은 PDF 1차 대조로 확정.

## 0. 결론 (한 화면)

사내 정보계에 **NICE 부동산 등기부 6테이블**(`CUWT_NIC_RLES_*`, 주제명역 `02.심사승인`)이 이미 적재되고 있다. 이는 폐쇄망에서 깨지는 현행 권리분석 파이프라인(**외부 등기부 발급 API(8100) → MinerU(8200) → gpt-4o PDF 파싱**)을 **결정적 구조화 DB 조회로 대체**한다.

핵심: 플랫폼이 이미 가진 목표 스키마 **`PropertyRightsData`**(`ownership_entries`/`ownership_other_entries`/`mortgage_entries`/`max_bond_amount`/`tenant_deposit`)에 6테이블이 거의 1:1로 매핑된다. 특히 LTV 분자의 핵심인 **`max_bond_amount` = SUM(저당명세 근저당 채권최고액)** 은 현재 LLM 추정값인데, NICE DB에선 **결정적 정확 합산**이 된다.

- **호단위 확정**: 부동산고유번호 = 전유부분(호) 1건. (CASE1 = 강서구 방화동 다세대 제3층 제302호, 전유 59.68㎡)
- **금액 원단위**: 채권최고액·거래가액 모두 원 그대로(`PDL_AMT`). KB시세의 만원→원 ×10000 **불필요**.
- **조인키 = 부동산고유번호**(`RLES_UNQ_NO`, 14자리, = 등기 고유번호). 파일명 `1149-1996-233513` ↔ `11491996233513` 일치.
- **주의 3대**: ① 조회시점 스냅샷이라 **신선도(`IQRY_DT`)** 가 생명 ② 주소·실명번호 **암호화** ③ enum **공통코드 master 필요**.

## 1. 6테이블 구조 · 키 계층

| 물리 테이블 | 엔티티 | 역할 | 행 성격 |
|---|---|---|---|
| `CUWT_NIC_RLES_CCRG_M` | 등기부등본**기본** | 1조회=1행 헤더. 압류/가압류/가처분/경매/근저당 **건수 집계** + 소재지 + 법정동 + **조회일자** + RLES_DVCD | 현재상태 |
| `CUWT_NIC_RLES_BRF_I` | **요약**명세 | 주요 등기사항 요약 = **현재 소유자/지분** | 현재상태 |
| `CUWT_NIC_RLES_COLL_I` | **저당**명세 | **현재 유효한 담보권**(근저당·전세권·질권) — 말소분 제외, 채권최고액+권리자 | 현재상태 ★ |
| `CUWT_NIC_RLES_HDR_D` | **표제부**상세 | 건물/전유부분 표시: 면적·구조·용도·호·대지권 | 정적(이력 표시번호) |
| `CUWT_NIC_RLES_CCRG_D` | 등기부등본**상세** | 갑구/을구 **전 등기라인 이력**(말소 포함) | 전체이력 |
| `CUWT_NIC_RLES_PDL_I` | **당사자**명세 | 각 등기라인의 당사자(소유자/채무자/권리자)+주소+금액, 말소분 포함 | 전체이력 |

**키 계층** (PK는 명세 PK POSITION 기준):
```
NICE_MSGM_NO   전문관리번호   = 1회 등기조회 트랜잭션 (샘플 실측 10자리; 명세는 14 표기 — 드리프트)
 └ RLES_UNQ_NO 부동산고유번호 = 물건(호) 14자리   ← ★ 플랫폼 조인키
    └ CCRG_DVCD  구분코드  1=갑구 / 2=을구  (상세·저당·당사자)
       └ CCRG_SEQNO  일련번호
          └ CCRG_COLL_SEQNO (저당)  /  CCRG_RANK_NO (표제부)
```
- 기본(M)은 `(NICE_MSGM_NO)` 단위 1행, 요약/표제부는 `+CCRG_SEQNO`, 저당/상세/당사자는 `+CCRG_DVCD+CCRG_SEQNO`.
- **현재상태 3테이블(기본·요약·저당)** = 심사가 바로 쓰는 "지금 권리관계". **전체이력 2테이블(상세·당사자)** = drill-down(소유권 변동 이력·과거 거래가액). 표제부 = 담보물건 제원.

## 2. 코드·열거값 (샘플 3 + PDF 역산 — ⚠️ 공통코드 master로 확정 필요)

| 컬럼 | 관측 코드 → 의미 (역산) |
|---|---|
| `CCRG_DVCD` 등기부구분 | `1`=갑구(소유권) · `2`=을구(소유권 이외). 표제부는 별도 테이블이라 코드 없음 |
| `RLES_DVCD` 부동산구분 | `3`=집합건물 (3케이스 모두 3; 단독/토지/상가 코드 미관측) |
| `RLES_PDL_DVCD` 당사자구분 | `21`=소유자 · `20`=채무자 · `46`=근저당권자 · `42`=전세권자 · `10`=질권채권자 (PDF 대조 역산) |
| `RGTY_PRPS_CD` 등기목적 | `C2313001`=근저당권설정 · `C2100001`=질권 (3케이스 근저당 모두 C2313001 일관) |
| `HDR_DTL_CD` 표제부상세 | C대=1동건물: `C11`소재지번 `C12`도로명 `C81`구조 `C82`지붕 `C83`/`C84`층수 `C87`용도 / E대=전유+대지권: `C13`접수일 `E41`~`E43`전유층·호 `E81`~`E83`전유구조·면적 `E61`대지권종류 `E71`대지권비율 |

`PDL_AMT_CTNT`(예 `금66,000,000원`)는 사람이 읽는 텍스트, `PDL_AMT`(`66000000`)는 숫자값 — **계산은 PDL_AMT 사용**.

## 3. NICE → `PropertyRightsData` 매핑 (★ 핵심)

플랫폼 목표 스키마는 이미 존재(`backend/models/response_models.py`, `frontend/src/types/loan.ts`, FE `PropertyRightsInfo.tsx`). 현행은 `ai_rights_analysis_service.generate_or_get_cached`가 PDF→LLM으로 채운다. **NICE DB는 동일 스키마를 결정적으로 채운다.**

| 플랫폼 필드 | ← NICE 출처 | 변환 |
|---|---|---|
| `ownership_entries[]` | **요약명세(BRF_I)** | name=`RGTY_NMNR_NM`, reg_number=`RNNO`(복호화→마스킹), share=`OWN_LAST_SHRS_CTNT`(예 "단독소유"), address=`RSDN_ADDR`(복호화), rank_number=`RGTY_RANK_NO` |
| `ownership_other_entries[]` (압류/가압류/가처분/경매) | **상세(CCRG_D)** WHERE `CCRG_DVCD='1'` AND 목적∈{압류,가압류,가처분,경매개시} | purpose=`RGTY_PRPS_CTNT`, receipt_info=`RGTY_ACTC_DT`+`RGTY_ACTC_NO`, details=당사자(PDL_I) join |
| `mortgage_entries[]` | **저당명세(COLL_I)** = 현재 유효분 | rank_number=`RGTY_RANK_NO`, purpose=`RGTY_PRPS_CTNT`, receipt_info=`RGTY_ACTC_DT`+`RGTY_ACTC_NO`, main_details=조합(채권최고액 `PDL_AMT` / 채무자 / 근저당권자 `RTP_NM`), target_owner=`TRGT_OWNR_NM` |
| **`max_bond_amount`** (LTV 분자) | **저당명세(COLL_I)** | **SUM(`PDL_AMT`) WHERE `RGTY_PRPS_CD`=근저당권설정**. 질권·전세권·이전·변경 제외 — 현 `ai_rights_analysis_service.py:36-45` 규칙과 동일하나 **추정 아닌 결정적**. (CASE1 검산: 신한 66,000,000 + 더빌캐피탈 75,000,000 = **141,000,000**; 질권 60M·말소 6건 제외) |
| `tenant_deposit` | 저당명세 전세권설정 `PDL_AMT` 합 | 등기된 전세권만. **미등기 임차(확정일자)는 등기부에 없음 → 0**(§5 caveat) |

**신규 제안 필드**(기본 M에 이미 집계되어 결정적 — 현재 LLM이 텍스트로 추정하던 것을 숫자로):
`seizure_count`←`SEIZ_CCNT` · `prov_seizure_count`←`PRSZ_CCNT` · `provisional_disp_count`←`PVSL_CCNT` · `auction_count`←`AUCT_OPNG_CCNT` · `mortgage_count`←`FXCL_CCNT` · `inquiry_date`←`IQRY_DT`(신선도 배지).

**담보물건(PropertyBasicInfo) 보강** — 표제부(HDR_D) 전유부분(E코드):
전유면적 ← `E82`/`E83`(예 59.68㎡) · 호 ← `E43`(제302호) · 대지권비율 ← `E71`(334분의 34.774) · 용도 ← `C87`(다세대주택) · 구조 ← `C81`. → 현행 `registry.py /{ic_id}/area`(PDF에서 전용면적 추출해 평형 추천)도 **DB 조회로 대체** 가능.

**과거 거래가액(실거래 보조)**: 갑구 소유권이전의 거래가액이 당사자명세(PDL_I, `CCRG_DVCD=1`)의 `PDL_AMT`에 있음(CASE1: 155,000,000 / 290,000,000). 정식 실거래(CCTR_APT_TXCS_HIST)와 별개의 호단위 보조 신호.

## 4. 아키텍처 — 현행 PDF→LLM 파이프 대체

**현행**(Explore 매핑): `LoanApplication.registry_ic_id`(Integer, 발급 마이크로서비스 8100 요청ID) → `registry.py`가 PDF blob → MinerU 8200 markdown → `ai_rights_analysis_service`(gpt-4o json) → `PropertyRightsData` + critique 루프. → **폐쇄망에서 외부 등기부 API·MinerU·외부 LLM 전부 리스크.**

**신규**:
1. **`registry_db_service`(신설, 앱 read-only)**: 부동산고유번호로 6테이블 조회 → `PropertyRightsData`를 **결정적 빌드**(LLM 무관). 숫자(max_bond_amount→LTV)는 완전 결정적.
2. **서술 요약**(`gap_summary`/`eul_summary`/`seizure_summary`/`priority_summary`)만 LLM 영역 → **사내 LLM 있으면** `LLMClient`(ADR-008) 경유, 없으면 규칙기반 요약 또는 생략. 핵심 수치 심사는 LLM 없이 성립.
3. **더미 차단**: `dummy_data.generate_property_rights_info`(random 채권최고액 5~10억) 미스 시 무경고 혼입 → 운영 전 차단(근거: `docs/dummy-vs-real.md`).

**적재 책임**: 이 6테이블은 **ADR-002의 수집기 소유 5테이블 밖** = 새 데이터 도메인(권리분석). `DW_LDNG_DTTM`(DW적재일시) 컬럼 = 이미 DW로 적재되는 정보계 자산. 선택지:
- (A) 수집기 ETL이 Oracle→PG 복제(부동산고유번호별 최신 스냅샷 upsert) — 다른 소스와 대칭, 앱은 read-only 유지. **권고**. 단 소유권 ADR 신설 필요.
- (B) 앱이 정보계 Oracle/DW를 직접 read-only — ADR-002 read-only 원칙과 정합하나 앱이 외부 DB 의존.

## 5. 운영 안전 3대 주의 (PDF 대조로 실증)

1. **신선도 — 스냅샷이다**: 기본행 `IQRY_DT`=조회시점. **CASE1 실증**: 원본 PDF(6/5 열람) 갑구 순위4에 **압류**(2026-05-11 접수)가 있으나, DB(`IQRY_DT`=20260413)는 `SEIZ_CCNT=0`. 압류가 DB 적재 후 발생 → 미반영. → **UI에 조회일자 배지 + N일 경과 경고 + 필요시 재조회 트리거 필수.** 스냅샷을 라이브로 오인하면 심사사고.
2. **암호화 — PII**: `LCTN_ADDR`(소재지)·`RSDN_ADDR`(거주지)·`PDL_ADDR`(당사자주소)·`RNNO`(실명번호)가 암호문(base64). ADR-010(PII 평문저장 금지) 정합. → 복호화 키/모듈 필요 여부 확인. **우회**: 주소 표시는 평문인 **표제부 `C11/C12`** 사용, 실명번호는 마스킹 그대로 노출.
3. **코드 master**: §2 enum은 샘플 3+PDF 역산. `RLES_PDL_DVCD`/`RGTY_PRPS_CD`/`HDR_DTL_CD`/`RLES_DVCD` 공통코드 테이블 확보 후 확정.

## 6. 이게 무엇을 해결하나 (feasibility 갱신 — 핸드오프 §3 보강)

| 기능 | 이전 | 등기부 DB 반영 후 |
|---|---|---|
| 권리분석(소유자·근저당·압류) | 🔴 PDF→MinerU→LLM, 폐쇄망 깨짐·추정오차 | 🟢 결정적 DB 조회 |
| LTV `max_bond_amount` | 🟡 LLM 추정(오염) | 🟢 SUM(저당명세) 정확 합산 |
| 등기부 발급 | 🔴 외부 발급 API(8100) | 🟢 내부 DB 조회 대체 |
| 담보물건 전유면적/호/대지권/용도 | 🟡 KB area 추정 | 🟢 표제부 보강 |
| 더미 폴백 오인 | 🔴 무경고 혼입 | 🟢 차단 근거 확정 |

**남는 약점**: ① **미등기 임차**(확정일자부 임차보증금)은 등기부에 없음 → 전입세대열람 등 별도(범위 밖이면 명시) ② 신선도 ③ 고유번호 1차 수기 입력 단계(심사자, §7-5) — 자동 연동은 2차.

## 7. 선결 확인 (probe·행정 — 이 환경에서 검증 불가)

1. 물리 테이블/스키마(`02.심사승인`) 접근권 + 위치(정보계 Oracle vs DW).
2. **공통코드 master** 4종(§2).
3. **암호화 복호 모듈/키** 제공 여부(없으면 §5-2 우회로 운영).
4. **적재 소유권 ADR** 신설(수집기 ETL vs 앱 직접) — §4.
5. ✅ **[결정됨] 부동산고유번호 ↔ 신청 매핑 = 고유번호 핸드오프**. 심사시스템 운영화면이 주소→고유번호 검색을 권위 있게 제공(도로명검색: 시도·시군구·도로명기본주소·동·호 / 지번검색: 시도·동리·지번·건물명칭·동·호 → 목록 선택 / 고유번호 직접검색). 이 검색·조회 UI는 **newtech-platform에서 호출 불가**(심사시스템 전용). → 심사자가 그 화면에서 검색·선택·조회로 얻은 **14자리 부동산고유번호를 신청 레코드에 입력/연동**, 앱은 그 키로만 6테이블을 읽는다. 표제부 평문 역매칭(구 후보②)은 **폐기**(검색 UI가 권위 해석기이므로 불필요). 현 `registry_ic_id`(Integer 발급ID) 자리를 14자리 고유번호 컬럼으로 대체. **1차=수기 입력**(형식검증 + 입력 즉시 6테이블 행 존재 확인 가드), **2차=심사시스템↔앱 키 연동**(수기 제거, 사내 협의).
6. `RLES_DVCD` 집합건물 외(단독/토지/상가) 케이스 표제부 레이아웃.
7. ✅ **[결정됨] 조회 트리거 = 심사자 수동**. NICE 조회·적재는 심사시스템 운영화면에서 심사자가 검색·선택·조회를 실행할 때 일어남(앱 자동 트리거 아님). → 앱은 조회 결과(6테이블)가 적재된 **이후** 고유번호로 읽는다. 고유번호 미입력/미조회 물건은 권리분석 不가용 → UI에 "등기 조회 선행 필요" 상태 표시. (잔여: 심사시스템↔앱 신청건 식별자 공유로 자동 연동 가능한지 = §7-5 2차.)
8. (명세 드리프트) `NICE_MSGM_NO` 길이(샘플 10 vs 명세 14), `GD_USG_NM`/`HDR_CTNT` 데이터타입 NUMBER 오기(실제 텍스트), 저당 `RLES_UNQ_NO` 길이 공란 — DDL 확정 시 정정.

## 8. 다음 단계

step4 사양 확정 → **`registry_db_service` 구현 + `PropertyRightsData` 결정적 빌드 + 더미 차단 + 신선도 UI**. 적재는 step2 ETL(수집기)과 함께. **선결 §7-5/§7-7 해소됨**(고유번호 핸드오프 + 심사자 수동 조회) → 신청→권리분석 연결 코드 작성 가능. 신청에 14자리 고유번호 컬럼 추가(현 `registry_ic_id` 대체) + 입력 가드 + `registry_db_service`가 그 키로 6테이블 결정적 빌드.
