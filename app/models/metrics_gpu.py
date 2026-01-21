from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricsGPU(Base):
    __tablename__ = "metrics_gpu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    utilization_percent: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    memory_used_mb: Mapped[int] = mapped_column(Integer, nullable=False)
