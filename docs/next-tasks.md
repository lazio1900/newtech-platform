# 다음 작업 목록

## 사용자가 요청한 작업 (미완료)
**"대시보드, 직접조회하기, 대부업체 신청건, 사후모니터링 — 더미 데이터를 DB화시켜서 실제 서비스로 만들기"**

이 작업은 계획 수립 중 사용자가 GitHub 저장소 생성/문서화 요청으로 전환하여 중단됨.

### 예상 작업 범위

#### Phase 1: DB 테이블 생성
- `users` 테이블 (인증)
- `loan_applications` 테이블 (대출 신청)
- `monitoring_loans` 테이블 (사후 모니터링)
- `search_history` 테이블 (자동완성)
- Alembic 마이그레이션 또는 Base.metadata.create_all

#### Phase 2: 백엔드 서비스 전환
- `auth_store.py` → DB ORM + bcrypt + JWT
- `application_store.py` → DB ORM (LoanApplication 모델)
- `monitoring_store.py` → DB ORM (MonitoringLoan 모델)
- `history_store.py` → DB ORM
- `main.py` 인라인 라우트 → 각 라우터 파일로 분리 권장

#### Phase 3: AI 분석 연동
- `claude_service.py` 활성화
- `analysis_service.py`에서 하드코딩된 분석 텍스트 → Claude API 호출
- ANTHROPIC_API_KEY 환경변수 설정 필요

#### Phase 4: 프론트엔드 (변경 최소)
- API 호출은 이미 실제 엔드포인트를 사용 중
- 백엔드가 같은 응답 형식을 유지하면 프론트 변경 불필요
- JWT 토큰 관리 추가 시 axios interceptor 설정

## 기타 개선 가능 항목
- [ ] Node.js 버전 업그레이드 (22.11 → 22.12+, Vite 권장)
- [ ] 로그인 시 JWT 토큰 기반 인증 + 미들웨어
- [ ] 차주/보증인 정보 직접 입력 UI (현재 더미 생성)
- [ ] 등기부등본 API 연동 (현재 더미)
- [ ] KB API 에러 핸들링 강화
- [ ] 프론트엔드 코드 스플리팅 (번들 978KB → 분할)
