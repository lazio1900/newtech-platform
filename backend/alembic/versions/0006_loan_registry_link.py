"""link loan_applications to registry_request via ic_id

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "loan_applications",
        sa.Column("registry_ic_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_loan_applications_registry_ic_id",
        "loan_applications",
        ["registry_ic_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_loan_applications_registry_ic_id", table_name="loan_applications")
    op.drop_column("loan_applications", "registry_ic_id")
