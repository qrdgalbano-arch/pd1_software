"""add component twin session metrics

Revision ID: 7c1d2e3f4a5b
Revises: 30bd78166036
Create Date: 2026-10-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "30bd78166036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("exercise_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("valid_repetitions", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("invalid_repetitions", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("incomplete_repetitions", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("arom_classification", sa.String(length=40), nullable=True)
        )
        batch_op.add_column(
            sa.Column("peak_rom_degrees", sa.Float(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("affected_side", sa.String(length=10), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("exercise_sessions") as batch_op:
        batch_op.drop_column("affected_side")
        batch_op.drop_column("peak_rom_degrees")
        batch_op.drop_column("arom_classification")
        batch_op.drop_column("incomplete_repetitions")
        batch_op.drop_column("invalid_repetitions")
        batch_op.drop_column("valid_repetitions")
