# 사내 데이터 이관 — ETL 적재기 사양 (step 2)

> 대상 레포 = **newtech_data / kb-estate-collector**(수집기). ADR-002상 `complexes/areas/kb_prices/transactions/listings` 소유=수집기, platform은 read-only. 따라서 Oracle→`kb_estate` 적재기는 수집기에 신설한다.
> 입력: [step1 field_mappings·로더 갭](internal-migration-field-mappings.md). 코드 근거는 수집기 `src/` 직접 분석 + 위험 가정 5건 적대적 검증으로 확정.

## 0. 아키텍처

신규 Oracle 소스를 수집기의 **기존 2단 패턴(connector=fetch/parse → Celery task=FK resolve·upsert)** 에 그대로 슬롯한다. 가장 최근 추가된 외부 소스(국토부 `molit_transaction`)가 1:1 청사진.

```
[Oracle thin connect → fetchmany 배치 SELECT]   connectors/oracle_internal.py  .fetch()
        ↓ field_mappings 14필드 정규화 + 변환(manwon_to_won·date_yyyymmdd…)   .parse()
[Postgres SessionLocal: M1/M2 룩업맵 → FK resolve → 2단계 실거래 매칭 → pg_insert.on_conflict 멱등 upsert]
        workers/tasks.py  ingest_oracle_*_task   (← 로더 갭 로직은 여기 신규 구현)
```

- **connector는 DB write 안 함** (수집기 `base.py` 계약 — fetch/parse만). FK resolve·적재 순서·M1/M2·2단계 매칭·skip+quarantine은 **tasks.py에 신규 작성**(기존 KB connector엔 없으므로 재사용 불가).
- Oracle 읽기(connector 내 별도 `oracledb.connect`)와 Postgres 적재(기존 `SessionLocal`, 5433 `kb_estate`)를 **절대 혼용 금지**.

## 1. 신설 컴포넌트

| 컴포넌트 | 경로 | 책임 |
|---|---|---|
| `OracleInternalConnector` | `src/connectors/oracle_internal.py` | `BaseConnector` 상속(molit과 동형). `fetch(table, watermark)`: oracledb thin connect → 테이블별 SELECT → `fetchmany` 스트리밍. `parse(rows)`: 14필드 정규화 + 변환 적용, 매칭 메타(`_kb_complex_id`,`_apt_name`)는 `_`접두사. oracledb는 함수 내 lazy import |
| Oracle connect 헬퍼 | 〃 | platform `db_connection_service.open_raw_connection` oracle 분기 **순수 connect 로직만** 이식(`oracledb.connect(dsn=host:port/service, tcp_connect_timeout=5)`). ORM(DbConnection) 의존부는 복사 말고 config 값으로 |
| Settings Oracle 필드 | `src/core/config.py` | `oracle_dsn/user/password`(Optional) + `oracle_etl_batch_size=5000`. `.env`로 주입. `database_url`(PG)과 분리 |
| `ingest_oracle_masters_task` | `src/workers/tasks.py` | complex→area **마스터 full 적재**. `backfill_kb_price_history_task` 구조 차용. complexes upsert→commit→areas 적재(M1 룩업) |
| `ingest_oracle_prices_task` / `ingest_oracle_transactions_task` | `src/workers/tasks.py` | 시계열 **증분 적재**. molit 태스크(`base=DatabaseTask,bind=True`) 정형. on_conflict 멱등 + skip/quarantine 카운트 |
| `EtlWatermark` 모델 + 마이그레이션 | `src/models/` + `src/alembic/versions/` | `etl_watermarks(source_table PK, last_watermark, updated_at)`. **+ `areas (complex_id,kb_area_code)` UNIQUE 신설**(아래 §3 멱등). 수집기 소유 alembic(`alembic_version`), autogenerate 시 platform 테이블 diff 제거 |
| task_routes + beat | `src/workers/celery_app.py` | `ingest_oracle_*` → 신규 **`etl` 큐**(KB fast/slow 미점유). beat 1엔트리(KB 가격잡 01·05·10·13시·discover 20시와 비충돌 시간대, 예 03시) |
| `oracledb>=2.0.0` | `requirements.txt` | **현재 부재 → 추가 필수**. thin-mode(인스턴트클라이언트 불필요, macOS prefork thick SIGSEGV 회피). 이미지 rebuild |

## 2. 추출 (Oracle SELECT)

| 엔티티 | 모드 | 워터마크 | SELECT 컬럼 |
|---|---|---|---|
| complex | 매번 full(소량) | — | `KB_QTN_RLES_GD_CD, APT_NM, ROAD_NM_BSIC_ADDR, KB_QTN_STDNG_CD, CMCN_YM, TOT_GEN_CNT, CNP_NM,CCW_NM,OLD_NM,EMD_NM,RI_NM,STAD_CTNT` |
| area | 매번 full(소량) | — | `KB_QTN_RLES_GD_CD, PNTP_SEQNO, EXUSE_ARE, PNTP_ARE` |
| kb_price | 증분 | **`DW_LDNG_DTTM`** | `KB_QTN_RLES_GD_CD, PNTP_SEQNO, IVST_BASE_DT, DEAL_GNRL_TXCS, DEAL_MXPR, DEAL_MNPR, DW_LDNG_DTTM` |
| transaction | 증분 | **`LAST_PROCS_DT`+`LAST_PROCS_TIME`** (★실거래엔 `DW_LDNG_DTTM` 없음) | `SEQNO, TX_DT, TX_AMT, APT_ARE, RLVN_FLR, KB_QTN_RLES_GD_CD, APT_NM, LAST_PROCS_DT, LAST_PROCS_TIME` |
| crosswalk(`CCTR_KB_APT_TXCS_MPNG_B`) | full(소량) → 메모리 dict | — | `KB_QTN_RLES_GD_CD, APT_NM` (정규화 `APT_NM`→KBA) |
| listing | — | — | 원천 없음 → 추출 제외(보류) |

- **워터마크 운용**: 첫 run은 watermark NULL→full 폴백. 이후 `WHERE <watermark> > :wm ORDER BY <watermark>`. 단조증가 미보장 가능성 대비 약간의 overlap(`>= wm - 여유`) 검토. run 종료 시 `etl_watermarks` commit.
- **샘플 확인됨**: KB계열(기본/시세/평형/법정동)에 `DW_LDNG_DTTM`(YYYYMMDDHHMMSS) 존재. 실거래는 `FRST_REG_DT`/`LAST_PROCS_DT`+`LAST_PROCS_TIME`만 → 그걸 워터마크로.
- 페이징은 OFFSET 대신 단일 커서 `fetchmany(arraysize=batch)` 스트리밍.

## 3. 적재 순서 & upsert (멱등)

부모→자식 단방향, FK는 태스크 시작 시 1회 빌드한 인메모리 룩업맵으로 resolve. 미스행은 **throw 아닌 skip+quarantine 로그**.

| 순서 | 엔티티 | FK resolve | 멱등키 / on_conflict | 반드시 주입(NOT NULL·default없음) |
|---|---|---|---|---|
| 1 | complexes | — | `kb_complex_id` UNIQUE → `on_conflict_do_update` | name, address |
| 2 | areas | complex_id=`M1[KB_QTN_RLES_GD_CD]` | ★`(complex_id,kb_area_code)` UNIQUE **신설 필요**(현재 부재) → 신설 후 on_conflict, 미신설 시 SELECT-후-분기 | complex_id, exclusive_m2 |
| 3 | transactions | complex_id=2단계매칭(아래) | `idx_transaction_unique(complex_id,contract_date,price,exclusive_m2,floor)` → `on_conflict_do_nothing` | complex_id, contract_date, price, exclusive_m2, fetched_at |
| 4 | kb_prices | complex_id=`M1`, area_id=`M2[(complex_id,PNTP_SEQNO)]` | `idx_kb_price_unique(complex_id,area_id,as_of_date)` → `on_conflict_do_nothing` | complex_id, area_id, as_of_date, fetched_at |
| 5 | listings | — | 보류(원천 없음) | — |

- **코어 `pg_insert`라 ORM default 미적용** → `is_active=True / priority=NORMAL / collect_listings=True / source='oracle' / created_at·fetched_at=now_kst()`를 전부 명시 주입.
- ⚠️ `floor=NULL`(RLVN_FLR 공백): PostgreSQL `NULL≠NULL`이라 `idx_transaction_unique` 멱등이 깨져 **중복 적재 가능** → NULL 빈도 확인 후 대체값(0/-1) 정규화 여부 결정.
- 룩업맵: `M1={kb_complex_id→complexes.id}`, `M2={(complex_id,kb_area_code)→areas.id}`. 기존 `_resolve_kb_*`(미발견 시 `ValueError raise`)는 ETL skip 요구와 상충 → `dict.get()→None 시 skip`으로 구현.

### 실거래 ↔ 단지 2단계 매칭 (complex_id)
1. `KB_QTN_RLES_GD_CD` 채워진 행 → `M1.get()`
2. 공백 행 → crosswalk dict(`정규화(APT_NM)→KBA`)로 보강 후 `M1.get()`
3. 그래도 미스 → 기존 `_match_complex_id(db, region, apt_nm)` fallback(region prefix+정규화+contains)
4. 전부 실패 → skip+quarantine (전체 미매칭 다수 = 표본 축소, step1 분석대로)

## 4. 변환

connector `parse()`에서 정규화 dict 생성 시 적용(molit이 가격 변환을 parse에서 하는 것과 동일). platform `data_transforms.py`와 **단위 동치 유지**(드리프트 = 원/만원 사고):
`manwon_to_won(×10000)` · `date_yyyymmdd`(→date 객체) · `built_year=year_from_date('YYYY.MM')` · `to_int/to_str/to_float` · `address=공백조인(주소 6조각)` · `region_code=dong_code[:5]` · `pyeong=round(EXUSE_ARE/3.305785,2)`.

## 5. 에러 처리 (3레벨)
1. **행**: FK 미해소·upsert키 NULL·필수 NOT NULL 누락·변환 None → INSERT 안 함, quarantine 카운트 + `logger.warning(원천식별자+사유)` (molit `skipped_unmatched` 패턴).
2. **배치**: 행 try/except로 한 행 실패가 배치를 안 죽임, `errors`+`continue`, `db.rollback()` 후 진행(backfill 패턴).
3. **태스크**: `try: commit / except: rollback+status=FAILED+error[:500] / finally: finished_at+commit` (molit 정형). `task_acks_late`+멱등 on_conflict라 재실행 안전.
- 반환 dict: `{processed, inserted, skipped_unmatched, quarantined, errors, max_watermark}`.

## 6. 스케줄
- 4태스크는 `autodiscover_tasks(['src.workers'])` 자동 등록. `task_routes`로 **`etl` 큐** 배정(KB fast/slow 미점유, head-of-line blocking 회피). docker-compose 워커에 `-Q etl` 추가.
- beat 디스패처 1엔트리: complexes→areas→prices→transactions 순서 enqueue. full/증분은 `etl_watermarks` NULL 여부로 자동 분기(첫 run full). 시간대는 KB 잡과 비충돌(예 `crontab(hour=3)`). RedBeat 자동 픽업(beat 재기동 금지).

## 7. 지오코딩 (step3로 분리)
Oracle에 lat/lng 없음 → 적재 시 `None`. 별도 `geocode_complexes_task`(`WHERE lat IS NULL AND address IS NOT NULL` 배치, road_address 우선)로 분리. 기존 수집기 좌표 출처는 KB detail API라 Oracle엔 적용 불가 → 외부 지오코더(카카오/네이버) 신설은 **step3 후속**. lat/lng nullable이라 미지오코딩 상태로도 적재 무결성 지장 없음(지도/인근동향만 제한).

## 8. 도입·검증 단계
0. requirements `oracledb` 추가→venv 재설치→`import oracledb` + `SELECT 1 FROM DUAL` 헬스체크
1. **추출 검증(read-only)**: `connector.fetch(table='complex', batch=10)` → 14필드 정규화 dict 확인. ★Oracle **물리 테이블명·컬럼명을 probe로 먼저 확인**(추측 금지)
2. **샘플 적재**: LIMIT 100 complexes→areas → Oracle count vs PG count vs quarantine 합 일치 확인
3. **FK·멱등**: prices/transactions 샘플 후 (a) FK NULL 없음 (b) 2회 재실행→`inserted=0`(멱등). areas UNIQUE 부재 시 중복 발생 여부 확인→마이그레이션 확정
4. **2단계 매칭**: KBA 공백 transaction 매칭률 + `skipped_unmatched` 점검
5. **증분**: 1차 full→watermark 저장→2차 run `processed` 급감 확인
6. **앱 read**: platform(8002) 분석 화면이 dummy 폴백 아닌 실데이터로 매칭되는지(ADR-002 read-only)
7. **큐 격리**: etl 큐가 KB 큐와 독립 동작 모니터

## 9. 선결 확인 / open questions
- **★Oracle 물리 테이블명·컬럼명 확정**: `CCTR_*` + `KB_QTN_RLES_GD_CD/PNTP_SEQNO/IVST_BASE_DT/TX_DT/SEQNO/DW_LDNG_DTTM`는 명세·샘플 기반. 실 Oracle DESCRIBE/probe로 검증(이 환경 접근 불가).
- **워터마크 검증**: `DW_LDNG_DTTM`(KB계열)·`LAST_PROCS_DT`(실거래)의 NOT NULL·단조증가 여부 → 증분 안정성. 미보장 시 overlap/보조컬럼.
- **`floor` NULL 빈도** → idx_transaction_unique 중복 적재 대응(대체값 vs 허용).
- **areas `(complex_id,kb_area_code)` UNIQUE 신설 승인**(수집기 소유 스키마 변경) — on_conflict 멱등 확보 vs SELECT-후-분기.
- **run/task 추적**(CrawlRun/CrawlTask) ETL 적용 여부(운영 가시성 vs 단순 반환 dict).
- crosswalk 1:N 충돌 시 우선순위 규칙.
- **스키마 드리프트(별건)**: 초기 마이그레이션이 `kb_prices.price/general_price`를 `Integer`로 생성(모델은 `BigInteger`). 원(만원→원) 적재 시 `Integer` 상한 위험 → 확인 필요.
- 지오코딩(step3) 제공자·API키·쿼터.

## 다음 단계
step 3 = **좌표/지오코딩 전략** 결정(§7) → 인근동향·지도·입지 활성화 여부. 또는 본 사양 기반 수집기 구현 착수.
