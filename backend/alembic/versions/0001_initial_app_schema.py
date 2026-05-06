"""initial app schema

본 앱 소유 테이블 5개 생성: users, loan_applications, monitoring_loans,
search_history, analysis_audit_logs (ADR-002, ADR-004~006).

수집기 소유 테이블(complexes, areas, kb_prices 등)은 별도 프로젝트가 관리.

Revision ID: 0001
Revises:
Create Date: 2026-05-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role_enum = postgresql.ENUM(
        "CUSTOMER", "AUDITOR", "ADMIN", name="userrole", create_type=False
    )
    application_status_enum = postgresql.ENUM(
        "RECEIVED", "REVIEWING", "APPROVED", "REJECTED", "ON_HOLD",
        name="applicationstatus", create_type=False,
    )
    search_field_enum = postgresql.ENUM(
        "COMPANY", "ADDRESS", name="searchfield", create_type=False
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)
    application_status_enum.create(op.get_bind(), checkfirst=True)
    search_field_enum.create(op.get_bind(), checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String(80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role_enum, nullable=False, server_default="CUSTOMER"),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("ceo_name", sa.String(80), nullable=True),
        sa.Column("business_number", sa.String(40), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_users_user_id", "users", ["user_id"], unique=True)

    # loan_applications
    op.create_table(
        "loan_applications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("applicant_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("auditor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("ceo_name", sa.String(80), nullable=False),
        sa.Column("property_address", sa.String(500), nullable=False),
        sa.Column("loan_amount", sa.BigInteger, nullable=False),
        sa.Column("loan_duration", sa.Integer, nullable=False, server_default="12"),
        sa.Column("status", application_status_enum, nullable=False, server_default="RECEIVED"),
        sa.Column("memo", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_loan_applications_applicant_user_id", "loan_applications", ["applicant_user_id"])
    op.create_index("ix_loan_applications_auditor_user_id", "loan_applications", ["auditor_user_id"])
    op.create_index("ix_loan_applications_status", "loan_applications", ["status"])
    op.create_index("ix_loan_applications_created_at", "loan_applications", ["created_at"])
    op.create_index("ix_loan_applications_status_created", "loan_applications", ["status", "created_at"])

    # monitoring_loans
    op.create_table(
        "monitoring_loans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("loan_code", sa.String(20), nullable=False, unique=True),
        sa.Column("auditor_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("auditor_name", sa.String(80), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("ceo_name", sa.String(80), nullable=False),
        sa.Column("property_address", sa.String(500), nullable=False),
        sa.Column("loan_amount", sa.BigInteger, nullable=False),
        sa.Column("execution_date", sa.Date, nullable=False),
        sa.Column("execution_price", sa.BigInteger, nullable=False),
        sa.Column("current_price", sa.BigInteger, nullable=False),
        sa.Column("last_evaluated_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_monitoring_loans_loan_code", "monitoring_loans", ["loan_code"], unique=True)
    op.create_index("ix_monitoring_loans_execution_date", "monitoring_loans", ["execution_date"])

    # search_history
    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("field", search_field_enum, nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_searched_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("field", "value", name="uq_search_history_field_value"),
    )
    op.create_index("ix_search_history_field_value", "search_history", ["field", "value"])

    # analysis_audit_logs
    op.create_table(
        "analysis_audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("property_address", sa.String(500), nullable=False),
        sa.Column("loan_amount", sa.BigInteger, nullable=False),
        sa.Column("llm_model", sa.String(80), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("response_summary", sa.Text, nullable=True),
        sa.Column("response_full", sa.Text, nullable=True),
        sa.Column("error_type", sa.String(80), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_analysis_audit_logs_user_id", "analysis_audit_logs", ["user_id"])
    op.create_index("ix_analysis_audit_logs_created_at", "analysis_audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("analysis_audit_logs")
    op.drop_table("search_history")
    op.drop_table("monitoring_loans")
    op.drop_table("loan_applications")
    op.drop_table("users")

    bind = op.get_bind()
    sa.Enum(name="searchfield").drop(bind, checkfirst=True)
    sa.Enum(name="applicationstatus").drop(bind, checkfirst=True)
    sa.Enum(name="userrole").drop(bind, checkfirst=True)
