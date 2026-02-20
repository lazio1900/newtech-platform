# KB Estate Platform - 프로젝트 문서

**질권 담보 대출 업무 플랫폼** - KB부동산 데이터를 수집하여 대출 심사를 지원하는 시스템

## 문서 목록

| 문서 | 내용 |
|------|------|
| [project-structure.md](project-structure.md) | 전체 디렉토리/파일 구조, API 엔드포인트, DB 모델 |
| [work-history.md](work-history.md) | 지금까지 수행한 작업 이력과 변경사항 |
| [dummy-vs-real.md](dummy-vs-real.md) | 더미/하드코딩 vs 실제 DB 데이터 현황 |
| [next-tasks.md](next-tasks.md) | 다음에 해야 할 작업 목록 |

## 기술 스택
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL(5433) + Redis(6379)
- **Frontend**: React 19 + TypeScript + Vite 7 + TanStack Query
- **외부 API**: KB부동산(api.kbland.kr), 국토부(MOLIT), Anthropic Claude
- **인프라**: Docker Compose

## 실행 방법
```bash
# 1. 인프라 (PostgreSQL + Redis)
cd newtech_merge && docker-compose up -d

# 2. 백엔드 (FastAPI)
cd newtech_merge/backend && .venv\Scripts\activate && uvicorn main:app --reload --port 8000

# 3. 프론트엔드 (React + Vite)
cd newtech_merge/frontend && npm run dev
```

## GitHub
- **Repository**: https://github.com/lazio1900/newtech-platform
- **Remote**: `mygithub` (lazio1900) / `origin` (choyoonjae1-newtech)

## 참고사항
- PostgreSQL 포트: **5433** (docker-compose에서 5433→5432 매핑)
- 인증: 하드코딩 (`customer`/`1`, `audit`/`1`) — DB화 예정
- Celery → **BackgroundTasks 전환 완료**
- Windows 환경 기준
