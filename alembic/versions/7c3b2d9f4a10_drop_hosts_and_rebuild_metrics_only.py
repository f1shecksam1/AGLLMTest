"""drop hosts and rebuild metrics tables without host-related columns

Revision ID: 7c3b2d9f4a10
Revises: 153d63076ab2
Create Date: 2026-01-21 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c3b2d9f4a10"
down_revision: Union[str, None] = "153d63076ab2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eski şemayı komple temizle (zaten verileri sileceğini söyledin)
    op.execute("DROP TABLE IF EXISTS metrics_gpu CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics_ram CASCADE;")
    op.execute("DROP TABLE IF EXISTS metrics_cpu CASCADE;")
    op.execute("DROP TABLE IF EXISTS hosts CASCADE;")

    # ✅ hosts yok
    # ✅ host_id / hostname yok

    op.create_table(
        "metrics_cpu",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usage_percent", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("freq_mhz", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metrics_cpu_ts"), "metrics_cpu", ["ts"], unique=False)

    op.create_table(
        "metrics_ram",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_mb", sa.Integer(), nullable=False),
        sa.Column("available_mb", sa.Integer(), nullable=False),
        sa.Column("usage_percent", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metrics_ram_ts"), "metrics_ram", ["ts"], unique=False)

    op.create_table(
        "metrics_gpu",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utilization_percent", sa.Float(), nullable=False),
        sa.Column("temperature_c", sa.Float(), nullable=False),
        sa.Column("memory_used_mb", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_metrics_gpu_ts"), "metrics_gpu", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_metrics_gpu_ts"), table_name="metrics_gpu")
    op.drop_table("metrics_gpu")

    op.drop_index(op.f("ix_metrics_ram_ts"), table_name="metrics_ram")
    op.drop_table("metrics_ram")

    op.drop_index(op.f("ix_metrics_cpu_ts"), table_name="metrics_cpu")
    op.drop_table("metrics_cpu")
