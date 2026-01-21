from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricsRAM(Base):
    __tablename__ = "metrics_ram"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    used_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    available_mb: Mapped[int] = mapped_column(Integer, nullable=False)
    usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
