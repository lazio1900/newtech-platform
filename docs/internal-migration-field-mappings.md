# 사내 데이터 이관 — field_mappings 초안 (step 1)

> 브랜치 `feat/internal-migration`. 사내 Oracle(스키마 `17.기준관리`)에 이미 쌓이는 KB/국토부 데이터를 원천으로, 앱 표준 5엔티티 조회 경로를 실데이터에 연결하기 위한 매핑 정의.
> 분석·판정 근거는 [[사내 KB Oracle 이관 분석]] 및 `docs/dummy-vs-real.md` 참조. 적재 아키텍처는 ADR-002(수집기 소유 read-only) 제약상 **ETL 적재 주체 = newtech_data**.

## 0. 핵심 결론

`DataSourceMapping.field_mappings` 의 `_validate` 가 **(key=entity_registry 표준필드) + (단일 source_field) + (등록된 transform)** 만 허용한다(`services/data_source_mapping_service.py:19-39`). 이 스키마로 표현 가능한 건 **단순 1:1 컬럼 변환 14개뿐**이고, 실제 적재 컬럼 기준 커버리지는 **30~35%**. 나머지(surrogate PK·FK resolve·주소 compose·파생·기본값·지오코딩·registry 비표준 모델컬럼)는 전부 **로더(ETL) 책임** → 그대로 step 2 ETL 사양으로 넘어간다.

| 엔티티 | field_mappings(선언) | 로더 갭 |
|---|---|---|
| complex | 5 | id, address, region_code, lat/lng, kb_complex_id, is_active |
| area | 2 | id, complex_id, pyeong, kb_area_code |
| kb_price | 4 | complex_id, area_id |
| transaction | 3 | id, complex_id, is_cancelled, floor, source_id, reported_date |
| listing | 0 | (원천 없음 — 전체 보류) |

---

## 1. 엔티티별 field_mappings (검증 완료 · `_validate` 통과)

`DataSourceMapping` 한 행당 `{logical_entity, source_table, field_mappings(JSON)}`. 아래 JSON 그대로 적재 가능.

### complex ← `CCTR_KB_APT_M`
```json
{
  "name":             { "source_field": "APT_NM",            "transform": "to_str" },
  "road_address":     { "source_field": "ROAD_NM_BSIC_ADDR", "transform": "to_str" },
  "dong_code":        { "source_field": "KB_QTN_STDNG_CD",   "transform": "to_str" },
  "built_year":       { "source_field": "CMCN_YM",           "transform": "to_str" },
  "total_households": { "source_field": "TOT_GEN_CNT",       "transform": "to_int" }
}
```
- `built_year`: 소스 `CMCN_YM`='YYYYMM'(6자). `year_from_date`는 date 입력 전제라 부적합 → `to_str` 원형보존. 앱이 `int(str(built_year)[:4])`로 연도 파싱하므로 동작은 정상이나 **`[:4]` 파싱 의존**이 남음(아래 신규 transform `yyyymm_to_year`로 해소 가능).

### area ← `CCTR_KB_APT_PNTP_I`
```json
{
  "exclusive_m2": { "source_field": "EXUSE_ARE", "transform": "to_float" },
  "supply_m2":    { "source_field": "PNTP_ARE",  "transform": "to_float" }
}
```

### kb_price ← `CCTR_KB_APT_QTN_L`
```json
{
  "as_of_date":     { "source_field": "IVST_BASE_DT",    "transform": "date_yyyymmdd" },
  "general_price":  { "source_field": "DEAL_GNRL_TXCS",  "transform": "manwon_to_won" },
  "high_avg_price": { "source_field": "DEAL_MXPR",       "transform": "manwon_to_won" },
  "low_avg_price":  { "source_field": "DEAL_MNPR",       "transform": "manwon_to_won" }
}
```
- ✅ **확인됨(현업)**: "평균가"의 기준은 **일반가** = `DEAL_GNRL_TXCS` → `general_price`(중심값). `high_avg_price`/`low_avg_price`는 KB 매매 **상한/하한가**(`DEAL_MXPR`/`DEAL_MNPR`)로 채운다 — 중심=일반가, 상/하한이 high/low 슬롯. **매핑 변경 없이 확정**.

### transaction ← `CCTR_APT_TXCS_HIST`
```json
{
  "exclusive_m2":  { "source_field": "APT_ARE", "transform": "to_float" },
  "contract_date": { "source_field": "TX_DT",   "transform": "date_yyyymmdd" },
  "price":         { "source_field": "TX_AMT",  "transform": "manwon_to_won" }
}
```

### listing ← (원천 없음)
```json
{}
```
매물호가 원천 테이블 미수집 → 전체 보류. 화면은 빈 상태로 안전 degrade(JB 가중 `W_NAVER=0`이라 LTV/공정가 무영향).

---

## 2. 로더(ETL) 갭 — step 2 사양으로 이관

`handling`: `surrogate_pk`(serial PK), `fk_resolve`(KBA→앱 id 룩업), `compose`(다중컬럼 조합), `derive`(파생), `default`(기본값 주입), `geocode`(지오코딩), `no_source`(원천 부재).

| 엔티티 | 필드 | handling | 규칙 |
|---|---|---|---|
| complex | id | surrogate_pk | serial PK. upsert 매칭키 = `kb_complex_id`(=`KB_QTN_RLES_GD_CD`) |
| complex | **address**(req) | compose | 공백조인(`CNP_NM, CCW_NM, OLD_NM, EMD_NM, RI_NM, STAD_CTNT`), null 조각 skip+trim |
| complex | **region_code**(req) | derive | `KB_QTN_STDNG_CD[:5]` (시군구 5자) |
| complex | lat/lng | geocode | 적재 후 주소 기반 외부 지오코딩 배치. 미수집 시 NULL |
| complex | kb_complex_id | (default/registry) | `KB_QTN_RLES_GD_CD` to_str — 모든 자식 FK resolve의 기준키 |
| complex | is_active | default | `True` 주입(또는 DB default). `real_data_service`의 nearby 후보 필터가 `is_active==True` 요구 |
| area | id / complex_id | surrogate_pk / fk_resolve | serial PK / `complexes.id WHERE kb_complex_id == KB_QTN_RLES_GD_CD` |
| area | pyeong | derive | `round(EXUSE_ARE / 3.305785, 2)` |
| area | kb_area_code | compose | `PNTP_SEQNO`(또는 `KBA-SEQNO` 복합). area_id 룩업 조인키 |
| kb_price | complex_id / area_id | fk_resolve | `kb_complex_id` 조인 / `areas WHERE complex_id=resolved AND kb_area_code==PNTP_SEQNO` |
| transaction | id / source_id | surrogate_pk | serial PK. `SEQNO` → `source_id`(to_str)로 보존 |
| transaction | **complex_id**(req) | fk_resolve(2단계) | ①`KB_QTN_RLES_GD_CD` 채워진 행은 `kb_complex_id` 조인 ②공백행은 `CCTR_KB_APT_TXCS_MPNG_B`(APT_NM↔KBA 크로스워크)로 보강. 미매칭 skip |
| transaction | is_cancelled | default | `False` 주입(해제여부 소스 컬럼 없음) |
| transaction | floor | (registry) | `to_int(RLVN_FLR)`. 멱등 UNIQUE 구성요소라 적재 필수 |
| transaction | reported_date | no_source | NULL(신고일 소스 없음) |
| listing | 전체 | no_source | 원천 미수집 → 적재 보류 |

### 적재 순서 & 룩업맵 (cross-entity FK resolve)
부모→자식 단방향, FK는 KBA 자연키 인메모리 룩업맵으로 resolve(미스행은 throw 아닌 **skip + quarantine 로그**).
1. **complexes** 적재(`kb_complex_id` upsert) → `M1 {kb_complex_id → complexes.id}`
2. **areas** 적재(`M1`로 complex_id resolve, `kb_area_code=PNTP_SEQNO` 보존) → `M2 {(complex_id, kb_area_code) → areas.id}`
3. **transaction**(`M1`로 complex_id, 공백행은 크로스워크 보강) / **kb_price**(`M1`로 complex_id → `M2`로 area_id)
4. **listing**: 원천 수집되면 `M1`/`M2` 동일 방식. 현재 보류

멱등키: complexes=`kb_complex_id` / areas=`(complex_id, kb_area_code)` / transaction=`UNIQUE(complex_id, contract_date, price, exclusive_m2, floor)` / kb_price=`idx_kb_price_unique(complex_id, area_id, as_of_date)`

---

## 3. 스키마 확장 제안 (선택 — 선언층 확대)

### 신규 transform (`entity_registry.TRANSFORM_REGISTRY` + `data_transforms.TRANSFORM_FUNCS`)
| key | 용도 | 추천 |
|---|---|---|
| `yyyymm_to_year` | `'YYYYMM'`→연도/`'YYYY.MM'`. complex.built_year를 선언층으로(앱 `[:4]` 의존 제거) | ✅ |
| `substr_5` | 10자 법정동코드 앞5자→region_code. 단일컬럼이라 스키마 호환 | ✅ |
| `m2_to_pyeong` | ㎡→평(÷3.305785). 상수 나눗셈 1건이라 로더 derive로 충분 | ❌ (YAGNI) |

### entity_registry 표준필드 추가 후보
- **`complex.kb_complex_id`** (1순위) — cross-entity resolve 핵심키. 추가 즉시 `to_str`로 field_mappings 흡수.
- `transaction.floor` / `transaction.source_id` — 단일컬럼(`RLVN_FLR`/`SEQNO`), 추가 시 선언 가능.
- `area.kb_area_code` — area_id 조인키. `PNTP_SEQNO` 단일로 확정되면 추가.
- `listing.source_listing_id` — 모델 필수(NOT NULL unique)인데 registry 누락. 원천 수집 시 필요.
- complex.lat/lng — 소스 부재라 추가해도 매핑 불가, geocode 로더 유지.

---

## 4. 다음 단계
step 2 = **ETL 적재기 사양**(수집기 newtech_data에 신설). 위 §2 갭 + §적재순서가 그 입력. 좌표(lat/lng) 지오코딩은 §2 P4의 별도 결정사항.
