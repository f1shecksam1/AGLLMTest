import re
from typing import Any

from jsonschema import validate
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.tools.registry import ToolRegistry

log = get_logger()

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-"
    r"[0-9a-fA-F]{12}$"
)


def sanitize_args(schema: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
    """
    LLM bazen:
      - sayıları string gönderir (örn "60")
      - host_id için <nil>/null/none gibi placeholder basar
      - required parametreyi hiç göndermeyebilir (schema default'ı varsa doldururuz)
    """
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

        # type list olabilir: ["integer","null"]
        expected_list: list[str] | None = None
        if isinstance(expected, list):
            expected_list = expected
            non_null = [t for t in expected if t != "null"]
            expected = non_null[0] if len(non_null) == 1 else None

        # 1) placeholder string -> None
        if isinstance(v, str):
            s = v.strip()
            if s.lower() in {"<nil>", "nil", "<null>", "null", "none", "<none>", ""}:
                clean[key] = None
                continue

        # 2) host_id özel: uuid değilse None'a çek (CAST patlamasın)
        if key == "host_id" and isinstance(clean.get(key), str):
            hs = clean[key].strip()
            if not _UUID_RE.match(hs):
                clean[key] = None
                continue

        # 3) integer
        if expected == "integer" and isinstance(v, str):
            s = v.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                clean[key] = int(s)

        # 4) number
        elif expected == "number" and isinstance(v, str):
            s = v.strip().replace(",", ".")
            try:
                clean[key] = float(s)
            except ValueError:
                pass

        # 5) boolean
        elif expected == "boolean" and isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "1", "yes", "y"}:
                clean[key] = True
            elif s in {"false", "0", "no", "n"}:
                clean[key] = False

        # 6) string bekleniyorsa primitive geldiyse string'e çevir
        elif expected == "string" and isinstance(v, (int, float, bool)):
            clean[key] = str(v)

        # null izinli değilse validate yakalar
        if clean.get(key) is None and expected_list and "null" not in expected_list:
            pass

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
