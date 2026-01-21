# app/llm/client.py
import httpx
from typing import Any

from app.core.config import settings

class LLMClient:  # Renamed from OpenAICompatClient
    def __init__(self) -> None:
        # Orchestrator uses client.model, so we must set it here
        self.model = settings.llm_model

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            # Note: We use settings.llm_base_url directly here
            r = await client.post(f"{settings.llm_base_url}/chat/completions", json=payload, headers=headers)
            r.raise_for_status()
            return r.json()