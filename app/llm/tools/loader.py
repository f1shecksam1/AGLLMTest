import json
from pathlib import Path

from app.llm.tools.types import ToolSpec


def load_tools(spec_dir: Path, sql_dir: Path) -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}

    for p in spec_dir.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        spec = ToolSpec.model_validate(data)

        sql_path = sql_dir / spec.x_sql_file
        if not sql_path.exists():
            raise RuntimeError(f"SQL file not found for tool={spec.name}: {sql_path}")

        spec.sql_text = sql_path.read_text(encoding="utf-8")
        tools[spec.name] = spec

    if not tools:
        raise RuntimeError(f"No tool specs found in {spec_dir}")

    return tools
