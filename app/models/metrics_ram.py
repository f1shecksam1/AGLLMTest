import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricsRAM(Base):
    __tablename__ = "metrics_ram"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    used_mb: Mapped[int] = mapped_column(Integer, nullable=False)              # 1
    available_mb: Mapped[int] = mapped_column(Integer, nullable=False)         # 2
    usage_percent: Mapped[float] = mapped_column(Float, nullable=False)        # 3

    __table_args__ = (
        Index("ix_metrics_ram_host_ts_desc", "host_id", "ts"),
    )
