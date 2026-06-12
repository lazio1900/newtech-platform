"""add snapshot fields to monitoring_loans (application_id / complex·area / prior_claims)

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("monitoring_loans", sa.Column("application_id", sa.String(length=36), nullable=True))
    op.add_column("monitoring_loans", sa.Column("complex_id", sa.Integer(), nullable=True))
    op.add_column("monitoring_loans", sa.Column("area_id", sa.Integer(), nullable=True))
    op.add_column(
        "monitoring_loans",
        sa.Column("prior_claims", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_index("ix_monitoring_loans_application_id", "monitoring_loans", ["application_id"])
    op.create_index("ix_monitoring_loans_complex_id", "monitoring_loans", ["complex_id"])


def downgrade() -> None:
    op.drop_index("ix_monitoring_loans_complex_id", table_name="monitoring_loans")
    op.drop_index("ix_monitoring_loans_application_id", table_name="monitoring_loans")
    op.drop_column("monitoring_loans", "prior_claims")
    op.drop_column("monitoring_loans", "area_id")
    op.drop_column("monitoring_loans", "complex_id")
    op.drop_column("monitoring_loans", "application_id")
