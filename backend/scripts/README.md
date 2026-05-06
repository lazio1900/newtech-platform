# scripts/

본 앱(newtech-platform) 관리용 운영 스크립트.

| 스크립트 | 용도 | 사용 시점 |
|---|---|---|
| `seed_users.py` | 기본 사용자 시드 (admin/audit/customer) | 개발 셋업 시 1회 |
| `seed_demo.py` | 데모 신청건/모니터링/검색이력 적재 | 개발 셋업 시 1회 |
| `_deprecated_init_collector_schema.py` | (폐기) 수집기 테이블 임시 생성 | **사용 금지** — newtech_data가 관리 |
| `_deprecated_seed_collector_demo.py` | (폐기) 단지 8개 임시 시드 | **사용 금지** — newtech_data가 적재 |

## deprecated 스크립트 안내

`_deprecated_*` 스크립트들은 newtech_data 프로젝트가 분리되기 전 임시 부트스트랩 용도였습니다.
이제 collector 영역(complexes, areas, kb_prices, transactions, listings, crawl_*)은
[newtech_data](file:///Users/lmj/00_projects/newtech_data/kb-estate-collector) 프로젝트가
자체 alembic으로 관리합니다 (INTEGRATION.md 참조).

본 앱이 자기 alembic으로 collector 테이블을 만들면 두 프로젝트의 마이그레이션이
충돌하므로, 위 스크립트들은 호출하지 마세요. 다음 정리 단계에서 완전 제거 예정.
