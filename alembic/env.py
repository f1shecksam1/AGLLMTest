import os
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # /app
sys.path.insert(0, str(PROJECT_ROOT))

config = context.config

# --- Autogenerate için modelleri import et ---
from app.models.base import Base  # noqa: E402
from app.models.metrics_cpu import MetricsCPU  # noqa: F401,E402
from app.models.metrics_ram import MetricsRAM  # noqa: F401,E402
from app.models.metrics_gpu import MetricsGPU  # noqa: F401,E402

target_metadata = Base.metadata


def get_url() -> str:
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC is not set")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
