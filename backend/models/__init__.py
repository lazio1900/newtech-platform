"""Database models package"""
from core.database import Base

# 본 앱 소유 (ADR-002: users / loan_applications / monitoring_loans / search_history / analysis_audit_logs)
from models.user import User, UserRole
from models.loan import (
    LoanApplication,
    MonitoringLoan,
    ApplicationStatus,
    APPLICATION_STATUS_LABELS,
    ALLOWED_TRANSITIONS,
)
from models.audit import SearchHistory, AnalysisAuditLog, SearchField
from models.data_source_mapping import DataSourceMapping
from models.db_connection import DbConnection
from models.llm_connection import LlmConnection
from models.llm_prompt import LlmPrompt

# 수집기 소유 (ADR-002: 본 앱은 read-only로 사용. ORM 매핑 유지)
from models.complex import Complex, Area, PriorityLevel
from models.price_data import KBPrice, Transaction, Listing, ListingStatus
from models.facility import ComplexFacility
from models.crawl import (
    CrawlJob,
    CrawlRun,
    CrawlTask,
    RawPayload,
    JobType,
    JobStatus,
    RunStatus,
    TaskStatus,
)

__all__ = [
    "Base",
    # 본 앱 소유
    "User",
    "UserRole",
    "LoanApplication",
    "MonitoringLoan",
    "ApplicationStatus",
    "APPLICATION_STATUS_LABELS",
    "ALLOWED_TRANSITIONS",
    "SearchHistory",
    "AnalysisAuditLog",
    "SearchField",
    "DataSourceMapping",
    "DbConnection",
    "LlmConnection",
    "LlmPrompt",
    # 수집기 소유 (read-only)
    "Complex",
    "Area",
    "PriorityLevel",
    "KBPrice",
    "Transaction",
    "Listing",
    "ListingStatus",
    "ComplexFacility",
    "CrawlJob",
    "CrawlRun",
    "CrawlTask",
    "RawPayload",
    "JobType",
    "JobStatus",
    "RunStatus",
    "TaskStatus",
]
