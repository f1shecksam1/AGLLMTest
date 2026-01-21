import asyncio
import json
import platform
import socket
import subprocess
from datetime import datetime, timezone
from typing import Any

import psutil
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.host import Host
from app.models.metrics_cpu import MetricsCPU
from app.models.metrics_ram import MetricsRAM
from app.models.metrics_gpu import MetricsGPU

log = get_logger()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _safe_cpu_temp() -> float | None:
    # psutil her platformda sıcaklık vermez; varsa alırız.
    try:
        temps = psutil.sensors_temperatures(fahrenheit=False)  # type: ignore[attr-defined]
        if not temps:
            return None
        # Yaygın anahtarlar: 'coretemp', 'k10temp' vs.
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
            "--query-gpu=utilization.gpu,temperature.gpu,memory.used,name",
            "--format=csv,noheader,nounits",
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()
        if not out:
            return None
        # Çok GPU varsa ilk satırı alıyoruz (sonra genişletiriz)
        parts = [p.strip() for p in out.splitlines()[0].split(",")]
        util = float(parts[0])
        temp = float(parts[1])
        mem_used = int(parts[2])
        name = parts[3] if len(parts) > 3 else None
        return {"util": util, "temp": temp, "mem_used": mem_used, "name": name}
    except Exception:
        return None


async def upsert_host(session: AsyncSession) -> Host:
    hostname = socket.gethostname()

    # Basit envanter
    os_name = platform.system()
    os_version = platform.version()

    cpu_model = platform.processor() or None
    cpu_cores = psutil.cpu_count(logical=False) or None
    cpu_threads = psutil.cpu_count(logical=True) or None

    vm = psutil.virtual_memory()
    ram_total_mb = int(vm.total / (1024 * 1024))

    gpu_info = _read_gpu_metrics_nvidia()
    gpu_name = gpu_info.get("name") if gpu_info else None

    existing = await session.execute(select(Host).where(Host.hostname == hostname))
    host = existing.scalar_one_or_none()

    if host is None:
        host = Host(
            hostname=hostname,
            os_name=os_name,
            os_version=os_version,
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            ram_total_mb=ram_total_mb,
            gpu_name=gpu_name,
        )
        session.add(host)
        await session.flush()
        log.info("collector.host.created", hostname=hostname, host_id=str(host.id))
        return host

    # Update (çok sık yazmamak için sadece değişirse update edebilirsin)
    await session.execute(
        update(Host)
        .where(Host.id == host.id)
        .values(
            os_name=os_name,
            os_version=os_version,
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_threads=cpu_threads,
            ram_total_mb=ram_total_mb,
            gpu_name=gpu_name,
        )
    )
    log.info("collector.host.updated", hostname=hostname, host_id=str(host.id))
    return host


async def collect_once(session: AsyncSession) -> None:
    ts = _now_utc()
    host = await upsert_host(session)

    # CPU
    cpu_usage = float(psutil.cpu_percent(interval=None))
    cpu_temp = _safe_cpu_temp()
    cpu_freq = _cpu_freq_mhz()

    session.add(
        MetricsCPU(
            host_id=host.id,
            ts=ts,
            usage_percent=cpu_usage,
            temperature_c=cpu_temp,
            freq_mhz=cpu_freq,
        )
    )

    # RAM
    vm = psutil.virtual_memory()
    used_mb = int(vm.used / (1024 * 1024))
    avail_mb = int(vm.available / (1024 * 1024))
    ram_pct = float(vm.percent)

    session.add(
        MetricsRAM(
            host_id=host.id,
            ts=ts,
            used_mb=used_mb,
            available_mb=avail_mb,
            usage_percent=ram_pct,
        )
    )

    # GPU (NVIDIA varsa)
    gpu = _read_gpu_metrics_nvidia()
    if gpu:
        session.add(
            MetricsGPU(
                host_id=host.id,
                ts=ts,
                utilization_percent=float(gpu["util"]),
                temperature_c=float(gpu["temp"]),
                memory_used_mb=int(gpu["mem_used"]),
            )
        )
    else:
        # GPU yoksa veya okunamadıysa istersen boş kayıt da atabilirsin (şimdilik atlamayı seçtim)
        log.info("collector.gpu.unavailable")

    await session.commit()

    log.info(
        "collector.metrics.written",
        ts=ts.isoformat(),
        host_id=str(host.id),
        cpu={"usage_percent": cpu_usage, "temperature_c": cpu_temp, "freq_mhz": cpu_freq},
        ram={"used_mb": used_mb, "available_mb": avail_mb, "usage_percent": ram_pct},
        gpu=gpu,
    )


async def run_forever() -> None:
    log.info("collector.start", interval_seconds=settings.metrics_interval_seconds)

    while True:
        try:
            async with SessionLocal() as session:
                await collect_once(session)
        except Exception:
            log.exception("collector.error")
        await asyncio.sleep(settings.metrics_interval_seconds)


def main() -> None:
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
