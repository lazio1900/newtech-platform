"""add complex/area/dong/ho columns to loan_applications

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 단지/평형 매칭 정보 (수집기 소유 테이블 참조 — FK 미설정. ADR-002)
    op.add_column("loan_applications", sa.Column("complex_id", sa.Integer, nullable=True))
    op.add_column("loan_applications", sa.Column("complex_name", sa.String(200), nullable=True))
    op.add_column("loan_applications", sa.Column("area_id", sa.Integer, nullable=True))
    op.add_column("loan_applications", sa.Column("exclusive_m2", sa.Float, nullable=True))
    op.add_column("loan_applications", sa.Column("pyeong", sa.Integer, nullable=True))
    op.add_column("loan_applications", sa.Column("dong", sa.String(40), nullable=True))
    op.add_column("loan_applications", sa.Column("ho", sa.String(40), nullable=True))

    op.create_index(
        "ix_loan_applications_complex_id", "loan_applications", ["complex_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_loan_applications_complex_id", table_name="loan_applications")
    op.drop_column("loan_applications", "ho")
    op.drop_column("loan_applications", "dong")
    op.drop_column("loan_applications", "pyeong")
    op.drop_column("loan_applications", "exclusive_m2")
    op.drop_column("loan_applications", "area_id")
    op.drop_column("loan_applications", "complex_name")
    op.drop_column("loan_applications", "complex_id")
