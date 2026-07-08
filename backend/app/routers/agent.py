from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..agent_engine import check_llm, run_agent
from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import User

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status", response_model=schemas.AgentStatus)
def agent_status(_: User = Depends(get_current_user)):
    if not settings.AGENT_ENABLED:
        return schemas.AgentStatus(enabled=False, llm_reachable=False, model=None)
    return schemas.AgentStatus(
        enabled=True, llm_reachable=check_llm(), model=settings.LLM_MODEL
    )


@router.post("/chat", response_model=schemas.AgentChatResponse)
def agent_chat(
    body: schemas.AgentChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not settings.AGENT_ENABLED:
        raise HTTPException(status_code=503, detail="AI agent is disabled (set AGENT_ENABLED=true)")
    if current_user.role.value == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot use the AI assistant")
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must not be empty")

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        reply, actions, explanation, pending = run_agent(messages, db, current_user.id)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Could not reach the local LLM. Check LLM_BASE_URL and that the model is running.",
        )
    return schemas.AgentChatResponse(
        reply=reply, actions=actions, explanation=explanation, pending_confirmation=pending
    )
