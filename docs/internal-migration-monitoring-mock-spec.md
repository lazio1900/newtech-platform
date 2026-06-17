# 사후 모니터링 정보계화 — 골든셋 기반 mock 데이터 스펙

> 목적: 사후 모니터링 화면(`MonitoringTab`)의 값을 사내 정보계 테이블에서 읽도록 바꾸기 전에,
> **등기부가 존재하는 골든셋**을 앵커로 정보계 7테이블을 self-consistent 하게 채워(=dev feeder)
> 읽기경로를 빌드·검증한다. 이 문서는 그 mock 데이터의 **단일 출처 스펙**이다.
>
> 위치(계약면): 기존 `scripts/build_cctr_from_crawl.py`(crawl→CCTR_*)·`scripts/load_nice_samples.py`(등기부→nice_rles_*)와
> 같은 dev-feeder 패턴. 운영 전환 시 이 mock 자리를 수집기 Oracle ETL이 대체한다(모드 런북 §5).
>
> 관련: `docs/internal-migration-mode-switch-runbook.md` / `docs/internal-migration-handoff.md` / 검증 워크플로 결과(이 작업 세션)

---

## 0-0. 상품 구조 (확정, 2026-06-16 사용자 확인)

**고객(`OCST_CUST_M`/`OCTR_LOAN_M.CSTNO`) = 차주 = 대부업체**(대부분 법인). 대부업체가 개인에게
부동산담보 대출을 실행(근저당 보유)하고, **당사(JB우리캐피탈)는 그 대부업체에 대출**(질권담보)한다.
따라서:
- 화면 '대부업체/회사명/대표자' = **`OCST_CUST_M.CUST_NM`/`TXNV_RPTV_NM`** (차주=대부업체).
- 담보 부동산 **실소유자 = 대부업체의 고객(개인)** = `OPDM_RLES_GD_D.RL_OWNR_NM`/`DBTR_NM` (차주 아님, 별도 표기).
- `OPDM_RLES_GD_D`의 `BRWR_*`(차주=대부업체) ↔ `ONCM_*`(당사=JB) 구분이 이 구조와 정합 → 화면 LTV는 **당사 기준 `ONCM_BND_HGST_AMT_LTV`** 라인.
- 주의: `OCST_CUST_M` 샘플의 개인·자영업명은 **전체 고객마스터 추출**(질권담보 차주만 필터 안 함) 때문. 실 차주는 상품코드(`GDS_CD`)로 질권담보를 걸러야 대부업체가 나옴 — 실건 트레이스 확인 항목.

## 0. mock이 푸는 것 / 안 푸는 것 (전제)

- **푼다(빌드·검증)**: 조인 무결성(#3)·현재시세 신선도(#2)를 내가 키/시점을 통제해 끝까지 잇는다 → 화면 읽기경로를 실제로 돌려볼 수 있음.
- **안 푼다**: ① 담당자 '이름'(직원마스터 부재 — mock은 placeholder), ② 운영 conformance(진짜 정보계가 이 키/신선도를 갖는지는 운영 전환 직전 **실건 1건 트레이스**로 별도 확인). `RLES_UNQ_NO` 운영 채움 여부도 거기서 확정.

---

## 1. 골든셋 인벤토리 (앵커 8건) + KB 단지 매칭 실측

출처: `openwebui_chatbot/ocr_task/기업금융팀/golden/extracted/<slug>.json` (실 등기부 OCR 파싱).
KB 매칭은 본 레포 PG `complexes`(45,962건) 실측(2026-06-16).

| slug | 등기부 부동산표시(단지/동·호) | 고유번호(→RLES_UNQ_NO 14자리) | KB 매칭 | kb_complex_id |
|---|---|---|---|---|
> **실측 갱신(2026-06-16, W2 빌드)**: 아래 표는 빌드 전 추정이었고 실제는 **6/8 매칭**. 정규화 적용 후 misa/sinchon/junggye/imin도 매칭됨. 미매칭은 areum/sinnae 2건뿐.

| slug | 등기부 부동산표시(단지/동·호) | 고유번호(→RLES_UNQ_NO 14자리) | KB 매칭(실측) | kb_complex_id |
|---|---|---|---|---|
| garak | 송파구 가락동 102 가락한신 102동 909호 | 1162-1996-097332 → `11621996097332` | ✅ 정확 | 1942 |
| mokdong | 양천구 신정동 1325 목동파크자이 105동 701호 | (json 고유번호) | ✅ 정확 | 35211 |
| misa | 하남시 풍산동 568 이편한세상미사 101동 2304호 | 〃 | ✅ 정규화(e편한세상미사) | 32809 |
| sinchon | 서대문구 북아현동 이편한세상신촌 203동 1704호 | 〃 | ✅ 정규화(e편한세상신촌) | 36279 |
| junggye | 노원구 중계동 중계2단지주공 | 〃 | ✅ 실재(KB명 '중계2단지주공') | 1046 |
| imin | 노원구 상계동 동아불암 | 〃 | ✅ 정확 | 971 |
| areum | 분당구 이매동 143 아름마을 706동 1603호 | 〃 | ❌ 빌더동 모호(한성/풍림/효성/선경/건영/태영 6개) | 시세결손 적재 |
| sinnae | 중랑구 신내동 650 신내아파트 607동 1202호 | 〃 | ❌ '신내아파트' 단일명 부재(6단지/9단지 모호) | 시세결손 적재 |

**시사점(중요)**: 8건 중 **매칭 6, 미매칭 2**(areum/sinnae — 같은 단지에 여러 빌더동/차수가 있어 동·주소만으론 특정 불가). 미매칭은 억지매칭 대신 시세결손(음성 케이스)로 적재됨. mock 매칭 규칙은 단순 동명(同名)이 아니라:
1. **단지명 정규화**: 공백 제거 + `이편한세상→e편한세상`, `(단지명)`/차수 토큰 분리.
2. **행정구역 핀**: `complexes.dong_name`·`region_code`(법정동 앞5)로 동명 단지 충돌 해소.
3. **동·호/전용면적**: 같은 단지 다(多)동이면 등기부 전유면적(`표제부` E82)으로 `areas.exclusive_m2` 최근접 평형 선택 → `KB_QTN_PNTP_SEQNO`.
4. **미매칭 정책**: 정규화 후에도 못 찾으면 그 건은 **현재시세 결손(확인불가) 상태로 적재** — 화면의 "시세 없음" 경로를 검증하는 음성 케이스로 활용(억지 매칭 금지). 중계주공2처럼 KB에 없는 건은 그대로 결손.

---

## 2. 식별·시세 브리지 (한 골든건이 끝까지 이어지는 사슬)

```
golden 등기부 ─(고유번호)→ RLES_UNQ_NO ─┐
                                        ├─ OCTR_LOAN_CMDT_M (대출물건)  ← LOANNO+GD_NO
golden 단지명/주소 ─(정규화 매칭)→ complexes.kb_complex_id (=KBA######)
   └→ areas.kb_area_code (=PNTP_SEQNO), exclusive_m2
        └→ OPDM_RLES_GD_D.KB_QTN_RLES_GD_CD / KB_QTN_PNTP_SEQNO
             └→ OCTR_KB_APT_QTN_L (시세)  ← 같은 KBA+PNTP, 최근 IVST_BASE_DT
```

- **현재시세(#2) 신선도**: mock `OCTR_KB_APT_QTN_L`은 가짜 숫자가 아니라 **매칭된 단지의 기존 `kb_prices` 최근값**을 만원 단위로 그대로 적재(원→만원 ÷10000, `build_cctr_from_crawl`의 역). → 2016 단발 샘플 문제 회피, 실데이터 신선도로 재평가 검증.
- **조인 무결성(#3)**: LOANNO·GD_NO·CSTNO·KBA를 한 건 안에서 일관 생성 → 6테이블이 실제로 join 됨.

---

## 3. 테이블별 mock 채움 사양

태그: **[실]** 골든/KB 실데이터 · **[파생]** 실데이터에서 계산 · **[합성]** 화면 검증용 합성(운영은 실값)

### 3.1 `OCST_CUST_M` (고객기본 — 차주)
| 컬럼 | 값 | 태그 |
|---|---|---|
| CSTNO | `GOLDEN<seq>` 16자 합성 | [합성] |
| CUST_NM | **대부업체명 합성**(차주=대부업체, §0-0 확정). 등기부 소유자는 여기 아님 → §3.4 RL_OWNR_NM | [합성] |
| CUST_TYCD | `2`(법인=대부업체) | [합성] |
| TXNV_RPTV_NM | 대표자명 placeholder | [합성] |

### 3.2 `OCTR_LOAN_M` (대출기본)
| 컬럼 | 값 | 태그 |
|---|---|---|
| LOANNO+LOAN_SEQNO | `26mmddNNNNN` + `01` 합성(11자) | [합성] |
| CSTNO | §3.1 동일 | [합성] |
| LOAN_PCPL(대출원금) | 합성(예: 매칭 시세의 50~70% LTV 역산), 원단위 | [합성] |
| LOAN_DT(실행일) | 합성 YYYYMMDD | [합성] |
| EXPR_DT/LOAN_INTRT | 합성(만기·금리) | [합성] |
| LOAN_STCD | `32`(정상) | [합성] |
| LNBZ_CHRG_EMPNO | placeholder(예: `MOCK0001`) — **이름 변환 불가(#1)** | [합성] |

> LOAN_PCPL_BAL(원금잔액)은 **비움**(STCD 32 진행건은 운영서도 공란/0). 잔액 기준 화면 아님 → §6.

### 3.3 `OCTR_LOAN_CMDT_M` (대출물건기본)
| 컬럼 | 값 | 태그 |
|---|---|---|
| LOANNO+LOAN_SEQNO+GD_NO | LOAN_M와 동일 LOANNO + `GD<seq>` 10자 | [합성] |
| RLES_UNQ_NO | 골든 고유번호 14자리(대시 제거) | [실] |
| GD_PRC(물건가격) | 매칭 KB 시세 또는 등기부 기준 | [파생] |
| APPC_AMT(신청금액) | = LOAN_PCPL | [합성] |
| SETP_AMT(설정금액) | 당사 근저당 설정액(예 대출금×1.1~1.3) | [합성] |
| PROR_SETP_AMT1 / PROR_RTP_NM | 선순위 설정금액 / 선순위권리자명 — 골든 을구 live 근저당 | [실] |
| MNGD_YN | `Y` | [합성] |

### 3.4 `OPDM_RLES_GD_D` (부동산물건상세 — 화면 값의 중심)
| 컬럼 | 값 | 태그 |
|---|---|---|
| GD_NO | §3.3 동일 | [합성] |
| CCRG_UNQ_NO | 골든 고유번호 | [실] |
| APT_NM | 골든 단지명(평문) | [실] |
| KB_QTN_RLES_GD_CD | 매칭 `complexes.kb_complex_id`(KBA######) | [파생] |
| KB_QTN_PNTP_SEQNO | 매칭 `areas.kb_area_code` | [파생] |
| KB_QTN_STDNG_CD | 매칭 법정동코드 | [파생] |
| EXUSE_ARE(전용㎡) | 등기부 전유면적 또는 매칭 area | [실/파생] |
| IVST_PRC / APLY_PRC(집행시세) | 실행시점 KB 시세 스냅샷(원) | [파생] |
| PROR_FCRG_TLAM(선순위근저당총액) | **골든 을구 live 근저당 채권최고액 합**(§5) | [실] |
| LODB_GUAR_AMT / LENT_GUAR_AMT | 전세/임대보증금(등기부 임차 or 0) | [실/합성] |
| LTV / APPC_LTV / ONCM_BND_HGST_AMT_LTV | 저장 LTV(집행시점) — (선순위+당사)/시세 ×100 | [파생] |
| DBTR_NM / RL_OWNR_NM | 등기부 채무자/현소유자명 | [실] |
| FMPS_NM(근저당권자명) | 골든 을구 선순위 권리자(예 송파농협) | [실] |
| CMCN_DT / MIH_YM / TOT_GEN_CNT | 매칭 단지 준공·세대수 | [파생] |

### 3.5 `OPDM_GD_ADRGRD_M` (물건주소지기본)
| 컬럼 | 값 | 태그 |
|---|---|---|
| GD_NO+GD_ADRGRD_SEQNO | §3.3 동일 + `1` | [합성] |
| ADDRSI/ADDR_GU/ADDONG/ADROAD | 골든 부동산표시 파싱(시/구/동/도로명, **평문**) | [실] |
| ADDR_DTAD/ADDR_DTAD2 | **mock은 평문**(운영은 암호문) — §6 | [실/합성] |

### 3.6 `OCTR_KB_APT_QTN_L` (KB아파트시세내역)
| 컬럼 | 값 | 태그 |
|---|---|---|
| KB_QTN_RLES_GD_CD+PNTP_SEQNO+IVST_BASE_DT | 매칭 KBA/평형 + 최근 조사일 | [파생] |
| DEAL_MNPR/DEAL_GNRL_TXCS/DEAL_MXPR | 매칭 `kb_prices` 하한/일반/상한(**만원**, ÷10000) | [실] |
| APT_NM/CCW_NM/EMD_NM/KB_QTN_STDNG_CD | 매칭 단지 메타 | [파생] |

> 미매칭 골든건은 이 테이블에 행 없음 → 현재시세 결손 케이스.

### 3.7 `OCTR_RGPL_LN_REPAY_L` (질권담보대출상환내역)
**현재 화면 불필요** → mock에서 **빈 테이블로 생성만**(스키마 존재). 향후 잔액/상환 화면 추가 시 채움.

---

## 4. 합성 규칙 (loan 레이어)

- 키 결정성: `slug` 인덱스 i → LOANNO=`2601` + (1000+i) + 체크, GD_NO=`GD000000{i}`, CSTNO=`GOLDEN{i:012d}`. (난수 금지 — 재현 가능)
- 금액: 매칭된 건은 **현재시세 기준 목표 LTV(예 60%)에서 LOAN_PCPL 역산** → 화면 LTV가 그럴듯하게 나오도록. 미매칭 건은 임의 금액 + 시세결손.
- 단위 일관: 대출/물건/상세 = **원**, KB시세 = **만원**. 적재 시 혼용 금지.

---

## 5. 선순위 근저당 합산 규칙 (골든 을구 → PROR_FCRG_TLAM)

- 대상: 을구 `말소=false`(live) 근저당권설정의 `채권최고액` 합.
- **실측(garak)**: live 근저당 7건 합 = **1,865,500,000원** (앞 초안의 799.6M은 truncated 샘플 오류였음).
- **⚠️ 빌드에서 드러난 문제 — LTV 과대계상**: 단순 live 합은 chain-말소(후순위 말소등기가 가리키는 앞순위 차감)를 반영 못 해, 누적 근저당을 과대 합산 → mock LTV가 대부분 100% 초과(garak 113.7%, mokdong 258%, misa 196%, sinchon 156%, imin 142%; junggye만 60%). **이건 mock이 등기부에서 선순위를 직접 derive한 산물**이지 시스템 결함 아님 — **운영 정보계는 `PROR_FCRG_TLAM`·`ONCM_BND_HGST_AMT_LTV`를 이미 정확히 계산해 보유**하므로 운영 화면 LTV는 정상.
- **결정/선택(§6-2)**: 그럴듯한 mock LTV가 필요하면 (a) W2 파서에 chain-말소 차감 추가, 또는 (b) 유효 선순위만(최신/우선순위) 채택. 현재 mock은 (전체 live 합)이라 '과대 LTV' 경로 검증용으로는 충분.

---

## 6. 적재 전 확정해야 할 결정 (mock이 강제로 드러내는 것)

1. ~~차주 의미~~ **확정(§0-0)**: 차주 = 대부업체 = `OCST_CUST_M.CUST_NM`. 담보 부동산 소유자(`RL_OWNR_NM`)는 별도. 당사=JB(`ONCM_*`).
2. **선순위 합산식**(§5): 전체 live 합 vs JB 기준 선순위만.
3. **담당자명(#1)**: placeholder 유지 vs 직원마스터 입수 시 실명. (mock 단계는 placeholder)
4. **주소 암호화**: mock 평문 유지(검증 편의). 운영 암호문 복호 모듈은 별도 트랙(handoff §4-bis).
5. **현재시세 출처**: mock·운영 모두 KB시세 테이블(`OCTR_KB_APT_QTN_L`=`kb_prices` 미러) 사용 확정. (수집기 KB 경로와 동일 계열)

---

## 7. 검증 기준선 (mock 적재 후 화면이 보여야 할 것)

- 매칭 골든건(예 가락한신·목동파크자이): 대출번호·차주·주소·대출금액·집행시세·**현재시세(최근)**·집행LTV·**현재LTV·변동**까지 전부 렌더(더미 아님).
- 미매칭 골든건(중계주공2 등): 대출/주소/선순위는 뜨되 **현재시세·현재LTV = 확인불가** 표시 — 음성 케이스.
- 상세 팝업: 등기부 권리분석이 골든 을구 기반으로 결정적 산출(RLES_UNQ_NO→`nice_rles_*` 이미 적재된 경로와 정합).

---

## 8. 빌드 방법 (다음 단계)

`scripts/build_monitoring_mock.py`(신규, dev 전용, `DATA_MODE=prod`에서 자가차단) — `build_cctr_from_crawl.py`+`load_nice_samples.py` 패턴:
1. golden `extracted/*.json` 로드 → 고유번호·을구·소유자·주소 추출.
2. `complexes`/`areas`/`kb_prices`에서 §1 규칙으로 단지·평형·시세 매칭.
3. 6테이블(+빈 REPAY) PG drop+create 후 적재. 매칭 실패는 시세결손으로 적재.
4. 적재 후 §7 기준선 카운트 출력(매칭/미매칭/시세보유 건수).

> ORM: 정보계 loan/물건/고객 테이블은 아직 `models/`에 없음 → 빌더와 함께 `models/internal_loan.py`(가칭) 신설 필요(수집기 소유 read-only, alembic 제외 — ADR-002/011 동일).
