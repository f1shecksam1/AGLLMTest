from typing import Any

from jsonschema import validate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.tools.registry import ToolRegistry

log = get_logger()


def sanitize_args(schema: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    props: dict[str, Any] = schema.get("properties", {}) or {}
    clean: dict[str, Any] = dict(args or {})

    # 0) schema default doldurma
    for key, prop in props.items():
        if key not in clean and "default" in prop:
            clean[key] = prop["default"]

    for key, prop in props.items():
        if key not in clean:
            continue

        v = clean[key]
        if v is None:
            continue

        expected = prop.get("type")
        if isinstance(expected, list):
            non_null = [t for t in expected if t != "null"]
            expected = non_null[0] if len(non_null) == 1 else None

        # 1) placeholder string -> None
        if isinstance(v, str):
            s = v.strip()
            if s.lower() in {
                "<nil>", "nil", "<null>", "null", "none", "<none>", "",
            }:
                clean[key] = None
                continue

        # 2) integer parse + clamp
        if expected == "integer" and isinstance(v, str):
            s = v.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                clean[key] = int(s)

        if expected == "integer" and isinstance(clean.get(key), int):
            if "minimum" in prop:
                clean[key] = max(clean[key], int(prop["minimum"]))
            if "maximum" in prop:
                clean[key] = min(clean[key], int(prop["maximum"]))

        # 3) number parse + clamp
        if expected == "number" and isinstance(v, str):
            s = v.strip().replace(",", ".")
            try:
                clean[key] = float(s)
            except ValueError:
                pass
        if expected == "number" and isinstance(clean.get(key), (int, float)):
            if "minimum" in prop:
                clean[key] = max(float(clean[key]), float(prop["minimum"]))
            if "maximum" in prop:
                clean[key] = min(float(clean[key]), float(prop["maximum"]))

        # 4) boolean
        if expected == "boolean" and isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "1", "yes", "y"}:
                clean[key] = True
            elif s in {"false", "0", "no", "n"}:
                clean[key] = False

        # 5) string bekleniyorsa primitive -> string
        if expected == "string" and isinstance(v, (int, float, bool)):
            clean[key] = str(v)

    # ✅ şemada olmayan anahtarları DROP et
    allowed = set(props.keys())
    clean = {k: v for k, v in clean.items() if k in allowed}

    return clean


async def execute_tool(
    registry: ToolRegistry,
    session: AsyncSession,
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    if not registry.has(tool_name):
        raise ValueError(f"Unknown tool: {tool_name}")

    spec = registry.get(tool_name)

    tool_args = sanitize_args(spec.parameters, tool_args)
    validate(instance=tool_args, schema=spec.parameters)

    log.info("tool.exec.start", tool_name=tool_name, tool_args=tool_args, sql_file=spec.x_sql_file)

    res = await session.execute(text(spec.sql_text or ""), tool_args)
    rows = res.mappings().all()

    if len(rows) == 1:
        result: dict[str, Any] = dict(rows[0])
    else:
        result = {"rows": [dict(r) for r in rows]}

    log.info("tool.exec.end", tool_name=tool_name, rowcount=len(rows), result=result)
    return result
