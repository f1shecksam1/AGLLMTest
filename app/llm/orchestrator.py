import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.client import OpenAICompatClient
from app.llm.tools.executor import execute_tool
from app.llm.tools.registry import ToolRegistry

log = get_logger()

_registry = ToolRegistry()
_client = OpenAICompatClient()


def _maybe_truncate(s: str, limit: int = 2000) -> str:
    return s if len(s) <= limit else s[:limit] + "...(truncated)"


async def ask_with_tools(session: AsyncSession, user_text: str) -> dict[str, Any]:
    log.info("llm.user_input", user_text=_maybe_truncate(user_text) if not settings.log_full_payload else user_text)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Sen bir araç seçme asistanısın. SQL üretme veya önermeye çalışma. "
                "Sadece uygun tool'u seç ve tool parametrelerini şemaya uygun ver. "
                "Tool yoksa bunu belirt."
            ),
        },
        {"role": "user", "content": user_text},
    ]

    tools = _registry.openai_tools()

    for i in range(settings.llm_max_tool_iterations):
        payload = {
            "model": settings.llm_model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        log.info("llm.request", iter=i, model=settings.llm_model, tools_count=len(tools))

        data = await _client.chat(payload)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        # Final cevap
        if not tool_calls:
            final_text = msg.get("content") or ""
            log.info("llm.final_answer", answer=_maybe_truncate(final_text) if not settings.log_full_payload else final_text)
            return {"answer": final_text, "used_tools": []}

        # Tool çağrısı varsa: önce assistant mesajını ekle
        messages.append({"role": "assistant", "tool_calls": tool_calls})

        used = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            tool_name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"
            tool_args = json.loads(raw_args)

            log.info("llm.tool_decision", tool_name=tool_name, tool_args=tool_args)

            result = await execute_tool(_registry, session, tool_name, tool_args)

            used.append({"tool": tool_name, "args": tool_args, "result": result})

            # Tool response mesajı
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        # Bir sonraki iterasyonda LLM tool sonuçlarıyla nihai cevap üretecek
        log.info("llm.tool_results.sent", tools_used=len(used))

    return {"answer": "Tool çağrıları çok uzadı; lütfen daha spesifik sor.", "used_tools": []}
