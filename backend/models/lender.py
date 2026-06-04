"""대부업체(차주) 마스터.

직접조회/케이스 등록 시 borrower 입력값을 upsert. business_number 가 있으면 그것으로
식별, 없으면 company_name. 신용점수는 최신 입력으로 갱신(누적 이력은 별도 테이블이
필요하면 추후).
"""
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from core.database import Base


class Lender(Base):
    __tablename__ = "lenders"

    id = Column(Integer, primary_key=True, index=True)

    company_name = Column(String(200), nullable=False, index=True, comment="대부업체 명칭")
    business_number = Column(String(20), nullable=True, comment="사업자등록번호")
    ceo_name = Column(String(80), nullable=True, comment="대표자명")
    credit_score_nice = Column(Integer, nullable=True, comment="대표자 NICE 신용점수(최신)")
    credit_score_kcb = Column(Integer, nullable=True, comment="대표자 KCB 신용점수(최신)")

    # 채무
    direct_debt = Column(BigInteger, nullable=True, comment="직접채무(원)")
    guarantee_debt = Column(BigInteger, nullable=True, comment="보증채무(원)")
    # 최근 3개년 재무 — [{year, assets, liabilities, equity, revenue, operating_profit, net_income}, ...]
    financial_data = Column(JSONB, nullable=True, comment="최근 3개년 재무 정보 (3행)")

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # business_number 가 NULL 인 row 는 UNIQUE 제약에서 제외되는 게 표준 SQL 동작
        UniqueConstraint("business_number", name="uq_lenders_business_number"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "company_name": self.company_name,
            "business_number": self.business_number,
            "ceo_name": self.ceo_name,
            "credit_score_nice": self.credit_score_nice,
            "credit_score_kcb": self.credit_score_kcb,
            "direct_debt": self.direct_debt,
            "guarantee_debt": self.guarantee_debt,
            "financial_data": self.financial_data,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M") if self.updated_at else None,
        }
