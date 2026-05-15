from datetime import datetime, date
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Float, Date, ForeignKey, Text, Index, Enum, Boolean
from sqlalchemy.orm import relationship
import enum
from core.database import Base


class ListingStatus(str, enum.Enum):
    """매물 상태"""
    ACTIVE = "active"
    SOLD = "sold"
    REMOVED = "removed"
    UNKNOWN = "unknown"


class KBPrice(Base):
    """KB 시세 스냅샷"""

    __tablename__ = "kb_prices"

    id = Column(Integer, primary_key=True, index=True)
    complex_id = Column(Integer, ForeignKey("complexes.id"), nullable=False)
    area_id = Column(Integer, ForeignKey("areas.id"), nullable=False)
    
    # 시세 데이터
    as_of_date = Column(Date, nullable=False, comment="기준일")
    general_price = Column(BigInteger, nullable=True, comment="일반가 (원)")
    high_avg_price = Column(BigInteger, nullable=True, comment="상위평균가 (원)")
    low_avg_price = Column(BigInteger, nullable=True, comment="하위평균가 (원)")
    
    # 메타데이터
    source = Column(String(50), default="kb", comment="데이터 소스")
    fetched_at = Column(DateTime, nullable=False, comment="수집 시각")
    payload_hash = Column(String(64), nullable=True, comment="원문 해시")
    parser_version = Column(String(20), nullable=True, comment="파서 버전")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    complex = relationship("Complex", back_populates="kb_prices")
    area = relationship("Area", back_populates="kb_prices")
    
    __table_args__ = (
        Index("idx_kb_price_unique", "complex_id", "area_id", "as_of_date", unique=True),
        Index("idx_kb_price_fetched", "fetched_at"),
    )


class Transaction(Base):
    """실거래가 레코드"""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    complex_id = Column(Integer, ForeignKey("complexes.id"), nullable=False)
    
    # 거래 정보
    contract_date = Column(Date, nullable=False, comment="계약일")
    price = Column(BigInteger, nullable=False, comment="거래가 (원)")
    exclusive_m2 = Column(Float, nullable=False, comment="전용면적 (㎡)")
    floor = Column(Integer, nullable=True, comment="층")
    
    # 추가 정보
    reported_date = Column(Date, nullable=True, comment="신고일")
    is_cancelled = Column(Boolean, default=False, comment="해제 여부")
    
    # 메타데이터
    source = Column(String(50), default="molit", comment="데이터 소스")
    source_id = Column(String(100), nullable=True, comment="원천 ID")
    fetched_at = Column(DateTime, nullable=False, comment="수집 시각")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    complex = relationship("Complex", back_populates="transactions")
    
    __table_args__ = (
        Index("idx_transaction_complex_date", "complex_id", "contract_date"),
        Index("idx_transaction_unique", "complex_id", "contract_date", "price", "exclusive_m2", "floor", unique=True),
    )


class Listing(Base):
    """매물/호가 레코드"""

    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    complex_id = Column(Integer, ForeignKey("complexes.id"), nullable=False)
    
    # 매물 정보
    source_listing_id = Column(String(100), unique=True, nullable=False, comment="원천 매물 ID")
    ask_price = Column(BigInteger, nullable=False, comment="호가 (원)")
    exclusive_m2 = Column(Float, nullable=True, comment="전용면적 (㎡)")
    floor = Column(Integer, nullable=True, comment="층")
    trade_type = Column(String(10), nullable=True, comment="거래유형: 매매 / 전세 / 월세")
    
    # 상태
    status = Column(Enum(ListingStatus), default=ListingStatus.ACTIVE, comment="매물 상태")
    posted_at = Column(DateTime, nullable=True, comment="등록일")
    status_updated_at = Column(DateTime, nullable=True, comment="상태 변경일")
    
    # 메타데이터
    source = Column(String(50), default="kb", comment="데이터 소스")
    fetched_at = Column(DateTime, nullable=False, comment="수집 시각")
    last_seen_at = Column(DateTime, nullable=False, comment="마지막 확인 시각")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    complex = relationship("Complex", back_populates="listings")
    
    __table_args__ = (
        Index("idx_listing_complex_status", "complex_id", "status"),
        Index("idx_listing_fetched", "fetched_at"),
    )
