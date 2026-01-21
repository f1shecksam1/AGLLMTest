from fastapi import APIRouter, Depends
from pydantic import BaseModel

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.llm.orchestrator import ask_with_tools

router = APIRouter(tags=["llm"])


class AskRequest(BaseModel):
    text: str


@router.post("/llm/ask")
async def ask(req: AskRequest, db: AsyncSession = Depends(get_db)):
    return await ask_with_tools(db, req.text)
