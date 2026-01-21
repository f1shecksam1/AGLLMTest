import asyncio
import subprocess
import random
from datetime import datetime, timezone
from typing import Any

import psutil

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.metrics_cpu import MetricsCPU
from app.models.metrics_ram import MetricsRAM
from app.models.metrics_gpu import MetricsGPU

log = get_logger()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _rand_float(lo: float, hi: float) -> float:
    return float(random.uniform(lo, hi))


def _rand_int(lo: int, hi: int) -> int:
    return int(random.randint(lo, hi))


def _safe_cpu_temp() -> float | None:
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)  # type: ignore[attr-defined]
        if not temps:
            return None
        for _, entries in temps.items():
            for e in entries:
                if e.current is not None:
                    return float(e.current)
        return None
    except Exception:
        return None


def _cpu_freq_mhz() -> float | None:
    try:
        f = psutil.cpu_freq()
        return float(f.current) if f and f.current is not None else None
    except Exception:
        return None


def _read_gpu_metrics_nvidia() -> dict[str, Any] | None:
    """
    NVIDIA varsa nvidia-smi ile:
    utilization.gpu (%), temperature.gpu (C), memory.used (MiB)
    """
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,temperature.gpu,memory.used",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        if not out:
            return None
        parts = [p.strip() for p in out.splitlines()[0].split(",")]
        util = float(parts[0])
        temp = float(parts[1])
        mem_used = int(parts[2])
        return {"util": util, "temp": temp, "mem_used": mem_used}
    except Exception:
        return None


async def collect_once() -> None:
    ts = _now_utc()

    async with SessionLocal() as session:
        # CPU
        cpu_usage = float(psutil.cpu_percent(interval=None))

        cpu_temp = _safe_cpu_temp()
        if cpu_temp is None:
            cpu_temp = _rand_float(35.0, 85.0)
            log.info("collector.cpu.temp.randomized", temperature_c=cpu_temp)

        cpu_freq = _cpu_freq_mhz()
        if cpu_freq is None:
            cpu_freq = _rand_float(1000.0, 5200.0)
            log.info("collector.cpu.freq.randomized", freq_mhz=cpu_freq)

        session.add(
            MetricsCPU(
                ts=ts,
                usage_percent=cpu_usage,
                temperature_c=float(cpu_temp),
                freq_mhz=float(cpu_freq),
            )
        )

        # RAM
        vm = psutil.virtual_memory()
        used_mb = int(vm.used / (1024 * 1024))
        avail_mb = int(vm.available / (1024 * 1024))
        ram_pct = float(vm.percent)

        session.add(
            MetricsRAM(
                ts=ts,
                used_mb=used_mb,
                available_mb=avail_mb,
                usage_percent=ram_pct,
            )
        )

        # GPU (NVIDIA yoksa bile random yaz)
        gpu = _read_gpu_metrics_nvidia()
        if gpu:
            util = float(gpu["util"])
            temp = float(gpu["temp"])
            mem_used = int(gpu["mem_used"])
        else:
            util = _rand_float(0.0, 100.0)
            temp = _rand_float(30.0, 95.0)
            mem_used = _rand_int(0, 16000)
            log.info("collector.gpu.randomized", util=util, temp=temp, mem_used=mem_used)

        session.add(
            MetricsGPU(
                ts=ts,
                utilization_percent=util,
                temperature_c=temp,
                memory_used_mb=mem_used,
            )
        )

        await session.commit()

    log.info(
        "collector.metrics.written",
        ts=ts.isoformat(),
        cpu={"usage_percent": cpu_usage, "temperature_c": cpu_temp, "freq_mhz": cpu_freq},
        ram={"used_mb": used_mb, "available_mb": avail_mb, "usage_percent": ram_pct},
        gpu={"util": util, "temp": temp, "mem_used": mem_used},
    )


async def run_forever() -> None:
    log.info("collector.start", interval_seconds=settings.metrics_interval_seconds)

    while True:
        try:
            await collect_once()
        except Exception:
            log.exception("collector.error")
        await asyncio.sleep(settings.metrics_interval_seconds)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
