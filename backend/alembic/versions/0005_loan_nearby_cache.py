"""add ai_nearby_text cache columns to loan_applications

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("loan_applications", sa.Column("ai_nearby_text", sa.Text(), nullable=True))
    op.add_column("loan_applications", sa.Column("ai_nearby_generated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("loan_applications", "ai_nearby_generated_at")
    op.drop_column("loan_applications", "ai_nearby_text")
