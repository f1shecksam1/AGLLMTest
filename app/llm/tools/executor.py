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
    LLM bazen sayıları string olarak gönderir (örn. "60") veya host_id için <nil> gibi placeholder basar.
    Bu fonksiyon schema'ya bakarak:
      - default değerleri doldurur
      - integer/number/boolean dönüşümü yapar
      - host_id placeholder/uuid olmayan string ise None'a çeker
    """
    props: dict[str, Any] = schema.get("properties", {}) or {}
    clean: dict[str, Any] = dict(args)

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

        # JSON Schema'da type bazen liste olabilir: ["integer","null"]
        expected_list: list[str] | None = None
        if isinstance(expected, list):
            expected_list = expected
            non_null = [t for t in expected if t != "null"]
            expected = non_null[0] if len(non_null) == 1 else None

        # 0.5) placeholder string -> None (özellikle host_id için)
        if isinstance(v, str):
            s = v.strip()
            if s.lower() in {"<nil>", "nil", "<null>", "null", "none", "<none>", ""}:
                clean[key] = None
                continue

        # host_id özel: uuid değilse None'a çek (CAST patlamasın)
        if key == "host_id" and isinstance(clean.get(key), str):
            hs = clean[key].strip()
            if not _UUID_RE.match(hs):
                clean[key] = None
                continue

        # integer
        if expected == "integer" and isinstance(v, str):
            s = v.strip()
            if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                clean[key] = int(s)

        # number (float)
        elif expected == "number" and isinstance(v, str):
            s = v.strip().replace(",", ".")
            try:
                clean[key] = float(s)
            except ValueError:
                pass

        # boolean
        elif expected == "boolean" and isinstance(v, str):
            s = v.strip().lower()
            if s in {"true", "1", "yes", "y"}:
                clean[key] = True
            elif s in {"false", "0", "no", "n"}:
                clean[key] = False

        # string bekleniyorsa ama sayı geldiyse -> stringe çevir (opsiyonel)
        elif expected == "string" and isinstance(v, (int, float, bool)):
            clean[key] = str(v)

        # Eğer schema type list ise ve clean None olduysa ama null izinli değilse geri alma (validate yakalar)
        if clean.get(key) is None and expected_list and "null" not in expected_list:
            # null izinli değilse validate patlasın (bilinçli)
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
