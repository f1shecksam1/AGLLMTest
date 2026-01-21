# app/llm/orchestrator.py
from __future__ import annotations

import json
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.llm.client import LLMClient
from app.llm.tools.executor import execute_tool
from app.llm.tools.registry import ToolRegistry

log = get_logger()

SYSTEM_PROMPT = """
Sen bir tool-orchestrator'sun.
- SQL üretme.
- Sadece verilen tool'ları seç ve çağır.
- host_id kullanıcı tarafından verilmemişse ASLA kullanıcıdan host_id isteme.
  Bunun yerine host_id parametresini OMIT et veya null gönder.
  (Sistem host_id null/olmaması durumunda otomatik en son host'u seçer.)
- minutes parametresi her zaman INTEGER olmalı (örn 60).
- Cevabı tool sonucu üzerinden ver; "imkansız" / "host_id yok" gibi kaçış cevapları verme.
""".strip()


def _looks_like_hostid_refusal(text: str) -> bool:
    t = (text or "").lower()
    if "host_id" not in t and "host id" not in t:
        return False
    return any(
        k in t
        for k in [
            "imkans",
            "imkansız",
            "cevap",
            "verilmiyor",
            "cannot",
            "can't",
            "impossible",
        ]
    )


async def ask_with_tools(session: AsyncSession, user_text: str) -> dict[str, Any]:
    registry = ToolRegistry()
    client = LLMClient()

    tools = registry.openai_tools()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    did_auto_select_host = False

    for i in range(5):
        log.info("llm.request", iter=i, model=client.model, tools_count=len(tools))

        payload = {
            "model": client.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        data = await client.chat(payload)

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}

        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content") or ""

        # 1) Tool çağrısı yok + "host_id lazım" kaçışı var -> fallback ile en son host'u resolve et
        if not tool_calls and not did_auto_select_host and _looks_like_hostid_refusal(content):
            try:
                snap = await execute_tool(registry, session, "get_latest_snapshot", {"host_id": None})
                snapshot_obj = snap.get("snapshot") or {}
                host_obj = snapshot_obj.get("host") or {}
                latest_host_id = host_obj.get("id")

                if latest_host_id:
                    did_auto_select_host = True
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                f"Host otomatik seçildi. Varsayılan host_id={latest_host_id}. "
                                "Kullanıcıdan host_id isteme; gerekiyorsa bunu kullan ya da host_id'yi null/omitted bırak."
                            ),
                        }
                    )
                    continue
            except Exception:
                log.exception("llm.fallback.latest_host_failed")

        # 2) Tool çağrısı yoksa: final answer
        if not tool_calls:
            log.info("llm.final_answer", answer=content)
            return {"answer": content}

        # 3) Tool çağrıları varsa: sırayla execute et
        messages.append(
            {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            }
        )

        for tc in tool_calls:
            fn = (tc.get("function") or {})
            tool_name = fn.get("name")
            raw_args = fn.get("arguments") or "{}"

            try:
                tool_args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except Exception:
                tool_args = {}

            log.info("llm.tool_decision", tool_name=tool_name, tool_args=tool_args)

            result = await execute_tool(registry, session, tool_name, tool_args)

            # IMPORTANT: datetime gibi tipleri güvenle JSON'a çevirmek için jsonable_encoder kullanıyoruz
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "name": tool_name,
                    "content": json.dumps(jsonable_encoder(result), ensure_ascii=False),
                }
            )

    return {"answer": "Tool çağrıları çok kez tekrarlandı; lütfen soruyu daha net sor."}
