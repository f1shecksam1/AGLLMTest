from pathlib import Path
from typing import Any

from app.llm.tools.loader import load_tools
from app.llm.tools.types import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        base = Path(__file__).resolve().parent
        self._tools: dict[str, ToolSpec] = load_tools(base / "specs", base / "sql")

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def openai_tools(self) -> list[dict[str, Any]]:
        return [spec.to_openai_tool() for spec in self._tools.values()]
