import httpx
from typing import Any

from app.core.config import settings


class OpenAICompatClient:
    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            r = await client.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
