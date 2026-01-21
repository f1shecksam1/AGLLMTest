from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetricsCPU(Base):
    __tablename__ = "metrics_cpu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    usage_percent: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    freq_mhz: Mapped[float] = mapped_column(Float, nullable=False)
