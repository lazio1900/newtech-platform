import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from core.database import Base


class ApplicationStatus(str, enum.Enum):
    """대출 신청 상태 머신 (ADR-006)

    전이 규칙:
      RECEIVED → REVIEWING → (APPROVED | REJECTED | ON_HOLD)
      ON_HOLD → REVIEWING
    """
    RECEIVED = "received"      # 접수완료
    REVIEWING = "reviewing"    # 심사중
    APPROVED = "approved"      # 승인
    REJECTED = "rejected"      # 반려
    ON_HOLD = "on_hold"        # 보류


# 한글 라벨 (UI/응답에서 사용)
APPLICATION_STATUS_LABELS = {
    ApplicationStatus.RECEIVED: "접수완료",
    ApplicationStatus.REVIEWING: "심사중",
    ApplicationStatus.APPROVED: "승인",
    ApplicationStatus.REJECTED: "반려",
    ApplicationStatus.ON_HOLD: "보류",
}

# 허용된 상태 전이
ALLOWED_TRANSITIONS = {
    ApplicationStatus.RECEIVED: {ApplicationStatus.REVIEWING, ApplicationStatus.REJECTED},
    ApplicationStatus.REVIEWING: {
        ApplicationStatus.APPROVED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.ON_HOLD,
    },
    ApplicationStatus.ON_HOLD: {ApplicationStatus.REVIEWING, ApplicationStatus.REJECTED},
    ApplicationStatus.APPROVED: set(),
    ApplicationStatus.REJECTED: set(),
}


class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id = Column(String(36), primary_key=True, comment="UUID")

    applicant_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    auditor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 신청 시점 스냅샷 (사용자 프로필이 바뀌어도 이력은 보존)
    company_name = Column(String(200), nullable=False)
    ceo_name = Column(String(80), nullable=False)
    property_address = Column(String(500), nullable=False, comment="전체 주소(표시용)")
    loan_amount = Column(BigInteger, nullable=False)
    loan_duration = Column(Integer, nullable=False, default=12, comment="개월")

    # 단지/평형 매칭 (수집기 소유 테이블 참조 — ADR-002에 따라 FK 미설정)
    complex_id = Column(Integer, nullable=True, index=True, comment="complexes.id, 매칭 안되면 NULL")
    complex_name = Column(String(200), nullable=True, comment="단지명 스냅샷")
    area_id = Column(Integer, nullable=True, comment="areas.id")
    exclusive_m2 = Column(Float, nullable=True, comment="전용면적(㎡) 스냅샷")
    pyeong = Column(Integer, nullable=True, comment="평수 스냅샷")
    dong = Column(String(40), nullable=True, comment="동 (예: 3동)")
    ho = Column(String(40), nullable=True, comment="호수 (예: 502호)")

    status = Column(
        Enum(ApplicationStatus),
        nullable=False,
        default=ApplicationStatus.RECEIVED,
        index=True,
    )
    memo = Column(Text, nullable=True)

    # AI 입지 분석 캐시 (LLM 응답) — 한 번 생성되면 재사용. NULL 이면 재생성 trigger
    ai_analysis_text = Column(Text, nullable=True, comment="LLM 입지 분석 결과(상세보기)")
    ai_analysis_generated_at = Column(DateTime, nullable=True)
    # AI 시세 분석 캐시
    ai_market_text = Column(Text, nullable=True, comment="LLM 시세 분석 결과(상세보기)")
    ai_market_generated_at = Column(DateTime, nullable=True)
    # AI 유사물건 분석 캐시
    ai_nearby_text = Column(Text, nullable=True, comment="LLM 유사물건 종합 코멘트")
    ai_nearby_generated_at = Column(DateTime, nullable=True)
    # 등기부등본 발급 결과 ic_id (registry_request 테이블 참조값, FK 미설정 — 별도 마이크로서비스)
    registry_ic_id = Column(Integer, nullable=True, index=True)
    # AI 권리 분석 캐시 (LLM 응답 — 좌측 요약 + 우측 줄글 통합 JSON)
    ai_rights_text = Column(Text, nullable=True, comment="LLM 권리 분석 (요약 + 줄글) JSON")
    ai_rights_generated_at = Column(DateTime, nullable=True)
    # AI 종합 의견 + 심사역 권고 캐시
    ai_overall_text = Column(Text, nullable=True, comment="LLM 종합 의견 + 심사역 권고 JSON")
    ai_overall_generated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True, comment="승인/반려 확정 시각")

    applicant = relationship("User", foreign_keys=[applicant_user_id])
    auditor = relationship("User", foreign_keys=[auditor_user_id])

    __table_args__ = (
        Index("ix_loan_applications_status_created", "status", "created_at"),
    )

    def to_dict(self) -> dict:
        status_value = self.status.value if isinstance(self.status, ApplicationStatus) else self.status
        status_label = (
            APPLICATION_STATUS_LABELS.get(self.status, status_value)
            if isinstance(self.status, ApplicationStatus)
            else status_value
        )
        return {
            "id": self.id,
            "applicant_user_id": self.applicant_user_id,
            "auditor_user_id": self.auditor_user_id,
            "company_name": self.company_name,
            "ceo_name": self.ceo_name,
            "property_address": self.property_address,
            "loan_amount": self.loan_amount,
            "loan_duration": self.loan_duration,
            "complex_id": self.complex_id,
            "complex_name": self.complex_name,
            "area_id": self.area_id,
            "exclusive_m2": self.exclusive_m2,
            "pyeong": self.pyeong,
            "dong": self.dong,
            "ho": self.ho,
            "registry_ic_id": self.registry_ic_id,
            # FE 호환: status는 한글 라벨로 노출. status_value는 enum 값.
            "status": status_label,
            "status_value": status_value,
            "memo": self.memo,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
            "decided_at": self.decided_at.strftime("%Y-%m-%d %H:%M") if self.decided_at else None,
        }


class MonitoringLoan(Base):
    """집행된 대출의 사후 모니터링.

    LTV / 신호등은 저장하지 않고 조회 시점에 계산 (current_price가 동적).
    """
    __tablename__ = "monitoring_loans"

    id = Column(Integer, primary_key=True, index=True)
    loan_code = Column(String(20), unique=True, nullable=False, index=True, comment="LN-YYYY-NNN")

    auditor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auditor_name = Column(String(80), nullable=False, comment="집행 시점 심사역명 스냅샷")

    company_name = Column(String(200), nullable=False)
    ceo_name = Column(String(80), nullable=False)
    property_address = Column(String(500), nullable=False)

    loan_amount = Column(BigInteger, nullable=False)
    execution_date = Column(Date, nullable=False, index=True)
    execution_price = Column(BigInteger, nullable=False, comment="집행 시점 시세")
    current_price = Column(BigInteger, nullable=False, comment="최신 추정 시세")

    last_evaluated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    auditor = relationship("User", foreign_keys=[auditor_user_id])

    @property
    def execution_ltv(self) -> float:
        if not self.execution_price:
            return 0.0
        return round(self.loan_amount / self.execution_price * 100, 1)

    @property
    def current_ltv(self) -> float:
        if not self.current_price:
            return 0.0
        return round(self.loan_amount / self.current_price * 100, 1)

    @property
    def ltv_change(self) -> float:
        return round(self.current_ltv - self.execution_ltv, 1)

    @property
    def signal(self) -> str:
        change = self.ltv_change
        if change <= 0:
            return "green"
        if change <= 3.0:
            return "yellow"
        return "red"

    @property
    def signal_label(self) -> str:
        return {"green": "안전", "yellow": "주의", "red": "위험"}[self.signal]

    def to_dict(self) -> dict:
        return {
            "loan_id": self.loan_code,
            "auditor_name": self.auditor_name,
            "company_name": self.company_name,
            "ceo_name": self.ceo_name,
            "property_address": self.property_address,
            "loan_amount": self.loan_amount,
            "execution_date": self.execution_date.strftime("%Y-%m-%d") if self.execution_date else None,
            "execution_price": self.execution_price,
            "current_price": self.current_price,
            "execution_ltv": self.execution_ltv,
            "current_ltv": self.current_ltv,
            "ltv_change": self.ltv_change,
            "signal": self.signal,
            "signal_label": self.signal_label,
        }
