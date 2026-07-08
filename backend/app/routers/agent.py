from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import agent_planner, schemas
from ..agent_engine import check_llm, run_agent
from ..auth import get_current_user, require_manager
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


# ---------------------------------------------------------------------------
# AI Project Planner (E4) — draft, refresh (deterministic), commit (explicit)
# ---------------------------------------------------------------------------

@router.post("/plan")
def plan(
    body: schemas.PlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Brief → validated draft plan. Never writes anything."""
    if not settings.AGENT_ENABLED:
        raise HTTPException(status_code=503, detail="AI agent is disabled (set AGENT_ENABLED=true)")
    try:
        raw = agent_planner.generate_raw_draft(body.brief, agent_planner.build_context(db))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Could not reach the local LLM. Check LLM_BASE_URL and that the model is running.",
        )
    return agent_planner.validate_and_enrich(
        db, raw, project_id=body.project_id, start_date=body.start_date
    )


@router.post("/plan/refresh")
def plan_refresh(
    body: schemas.PlanRefreshRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Re-validate + re-schedule an edited draft. Deterministic; no LLM, no writes."""
    start = body.start_date or _parse_iso(body.draft.get("start_date"))
    return agent_planner.validate_and_enrich(
        db,
        body.draft,
        project_id=body.project_id or body.draft.get("project_id"),
        start_date=start,
    )


@router.post("/plan/commit")
def plan_commit(
    body: schemas.PlanCommitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
):
    """Create the reviewed draft's requests/tasks/dependencies. The manager's
    click IS the confirmation; everything lands in AuditLog via the agent tools."""
    result = agent_planner.commit_plan(db, body.draft, current_user.id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


def _parse_iso(value) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None
