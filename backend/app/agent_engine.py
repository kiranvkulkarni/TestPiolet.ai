"""LLM tool-calling loop for the built-in AI assistant.

Talks to a local, OpenAI-compatible LLM (Ollama / Samsung Gauss / Intel
OpenVINO) via the `openai` client. All DB access goes through `agent_tools`.
"""

import json
import logging

from openai import OpenAI
from sqlalchemy.orm import Session

from . import agent_tools
from .config import settings

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10

SYSTEM_PROMPT = """You are the AI assistant inside a QA Task Assigner used by a Samsung \
Android camera QA team. You help the manager and testers assign test tasks, check \
workload, update task statuses, and plan test work. Today's tasks live in a database you \
access ONLY through your tools.

The 15 valid task_type values (use them exactly):
functional_sanity, functional_full_sanity, functional_feature_verification, \
functional_menu_tree, issue_reproduction, fix_verification, side_effect_verification, \
nonfunc_kpi_launch_time, nonfunc_fps, nonfunc_memory_profiling, nonfunc_memory_leak, \
nonfunc_power_consumption, compliance_google_its, compliance_google_cts, \
compliance_sensor_fusion.

Valid status values: pending, in_progress, blocked, completed, cancelled.
Valid priority values: critical, high, medium, low.

Workflow discipline — always follow it:
1. Before assigning work, call get_workload_summary (or find_underloaded_testers) and \
prefer less-loaded testers.
2. Before creating a task, fetch a valid test_request_id with get_test_requests (or \
get_projects first). Never invent IDs.
3. When the user names a device, resolve it to a device_model_id with get_device_models.
4. When dates are given for an assignee, call check_leave_conflicts and warn about \
overlaps before proceeding.
5. Bulk actions (5+ tasks): the write tools return needs_confirmation with a plan \
instead of committing. Present that plan clearly and ask the user to confirm. Only \
after the user explicitly says yes, call the same tool again with confirm=true. Never \
set confirm=true on your own.
6. To reschedule or rebalance work, prefer the purpose-built tools (reschedule_tasks, \
assign_bulk, set_dependency, remove_dependency) over many update_task calls — they \
respect working calendars and return an explanation.
7. When a task is marked completed, offer to record actual_hours.
8. If a request is ambiguous, ask ONE clarifying question instead of guessing.

Write tools return a rationale and confidence — repeat the key facts from the rationale \
in your reply so the user knows what changed and why. Be concise. Dates are YYYY-MM-DD."""


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_team_members",
            "description": "List active team members with their id, name, email and role.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_workload_summary",
            "description": "Current workload per tester: active task count and estimated hours. Call before assigning work.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_projects",
            "description": "List projects with id, name and status.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_test_requests",
            "description": "List test requests (id, title, project, status). Use to find a valid test_request_id before creating tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "Filter by project id"},
                    "status": {
                        "type": "string",
                        "enum": ["open", "in_progress", "completed", "cancelled"],
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "List tasks, optionally filtered by status, assignee, project, or overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "blocked", "completed", "cancelled"],
                    },
                    "assigned_to": {"type": "integer", "description": "User id of the assignee"},
                    "project_id": {"type": "integer"},
                    "overdue": {"type": "boolean", "description": "Only tasks past their due date"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_device_models",
            "description": "List active device models (id, brand, series, model_name, os_version). Use to resolve device names to ids.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_leave_conflicts",
            "description": "Check whether a user has approved leave overlapping a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "integer"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["user_id", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create one task under an existing test request. Fetch a valid test_request_id first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_request_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "task_type": {
                        "type": "string",
                        "enum": sorted(agent_tools.VALID_TASK_TYPES),
                    },
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "assigned_to": {"type": "integer", "description": "User id of the assignee"},
                    "device_model_id": {"type": "integer"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "estimated_hours": {"type": "number"},
                    "build_version": {"type": "string"},
                },
                "required": ["test_request_id", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tasks_bulk",
            "description": "Create several tasks at once. Each item has the same fields as create_task. Confirm with the user before creating 5 or more.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tasks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "test_request_id": {"type": "integer"},
                                "title": {"type": "string"},
                                "task_type": {
                                    "type": "string",
                                    "enum": sorted(agent_tools.VALID_TASK_TYPES),
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["critical", "high", "medium", "low"],
                                },
                                "assigned_to": {"type": "integer"},
                                "device_model_id": {"type": "integer"},
                                "start_date": {"type": "string"},
                                "due_date": {"type": "string"},
                                "estimated_hours": {"type": "number"},
                            },
                            "required": ["test_request_id", "title"],
                        },
                    }
                },
                "required": ["tasks"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "Update fields on an existing task (status, assignee, dates, priority, hours, ...).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "blocked", "completed", "cancelled"],
                    },
                    "priority": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                    "assigned_to": {"type": "integer"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "estimated_hours": {"type": "number"},
                    "actual_hours": {"type": "number"},
                    "device_model_id": {"type": "integer"},
                },
                "required": ["task_id"],
            },
        },
    },
]

TOOLS += [
    {
        "type": "function",
        "function": {
            "name": "reschedule_tasks",
            "description": "Move one or more tasks to a new start date. Respects weekends and each assignee's approved leave, and pushes dependent tasks forward if needed. For 5+ tasks it returns a plan needing user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_ids": {"type": "array", "items": {"type": "integer"}},
                    "start_date": {"type": "string", "description": "New start date, YYYY-MM-DD"},
                    "confirm": {
                        "type": "boolean",
                        "description": "Set true ONLY after the user explicitly confirmed the proposed plan",
                    },
                },
                "required": ["task_ids", "start_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_dependency",
            "description": "Create a finish-to-start dependency: from_task must finish before to_task starts. Rejects cycles and duplicates; pushes the successor if its dates violate the new link.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_task_id": {"type": "integer", "description": "The predecessor (finishes first)"},
                    "to_task_id": {"type": "integer", "description": "The successor (waits for the predecessor)"},
                },
                "required": ["from_task_id", "to_task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_dependency",
            "description": "Remove the finish-to-start dependency between two tasks. Never changes dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_task_id": {"type": "integer"},
                    "to_task_id": {"type": "integer"},
                },
                "required": ["from_task_id", "to_task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "assign_bulk",
            "description": "Assign or reassign a set of tasks across active testers, balancing by estimated hours (largest task to least-loaded tester) and avoiding approved leave. Use exclude_user_ids to move work OFF someone. For 5+ tasks it returns a plan needing user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_ids": {"type": "array", "items": {"type": "integer"}},
                    "exclude_user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Tester ids who must NOT receive these tasks",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "Set true ONLY after the user explicitly confirmed the proposed plan",
                    },
                },
                "required": ["task_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_critical_path",
            "description": "The ordered chain of zero-slack tasks that determines the project end date, plus the computed end date. Optionally scoped to one project.",
            "parameters": {
                "type": "object",
                "properties": {"project_id": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_underloaded_testers",
            "description": "Testers whose active estimated hours are below a threshold (default: team average). Use before assigning new work.",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold_hours": {"type": "number", "description": "Load threshold in hours"}
                },
            },
        },
    },
]

TOOL_FN_MAP = {
    "get_team_members": agent_tools.get_team_members,
    "get_workload_summary": agent_tools.get_workload_summary,
    "get_projects": agent_tools.get_projects,
    "get_test_requests": agent_tools.get_test_requests,
    "get_tasks": agent_tools.get_tasks,
    "get_device_models": agent_tools.get_device_models,
    "check_leave_conflicts": agent_tools.check_leave_conflicts,
    "create_task": agent_tools.create_task,
    "create_tasks_bulk": agent_tools.create_tasks_bulk,
    "update_task": agent_tools.update_task,
    "reschedule_tasks": agent_tools.reschedule_tasks,
    "set_dependency": agent_tools.set_dependency,
    "remove_dependency": agent_tools.remove_dependency,
    "assign_bulk": agent_tools.assign_bulk,
    "get_critical_path": agent_tools.get_critical_path,
    "find_underloaded_testers": agent_tools.find_underloaded_testers,
}

WRITE_TOOLS = {
    "create_task",
    "create_tasks_bulk",
    "update_task",
    "reschedule_tasks",
    "set_dependency",
    "remove_dependency",
    "assign_bulk",
}


def _client() -> OpenAI:
    return OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY)


def check_llm() -> bool:
    """Cheap reachability probe for /agent/status."""
    try:
        _client().models.list()
        return True
    except Exception:
        return False


def run_agent(
    messages: list[dict], db: Session, current_user_id: int | None = None
) -> tuple[str, list[dict], list[dict], bool]:
    """Run the tool loop.

    Returns (reply text, actions taken, explanation, pending_confirmation) —
    `explanation` is one {tool, rationale, confidence} entry per committed write;
    `pending_confirmation` is True when a bulk tool returned a plan awaiting an
    explicit user yes (nothing was committed for that call).
    """
    client = _client()
    convo: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
    actions: list[dict] = []
    explanation: list[dict] = []
    pending_confirmation = False

    for _ in range(MAX_ITERATIONS):
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=convo,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            return message.content or "", actions, explanation, pending_confirmation

        convo.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
        )

        for tc in message.tool_calls:
            name = tc.function.name
            fn = TOOL_FN_MAP.get(name)
            try:
                args = json.loads(tc.function.arguments or "{}")
                if not isinstance(args, dict):
                    args = {}
            except json.JSONDecodeError:
                args = {}

            if fn is None:
                result = {"error": f"unknown tool '{name}'"}
            else:
                try:
                    if name in WRITE_TOOLS:
                        result = fn(db, current_user_id=current_user_id, **args)
                    else:
                        result = fn(db, **args)
                except Exception:
                    logger.exception("Agent tool %s failed", name)
                    db.rollback()
                    result = {"error": f"tool '{name}' failed unexpectedly"}

            if name in WRITE_TOOLS and "error" not in result:
                if result.get("needs_confirmation"):
                    pending_confirmation = True
                else:
                    actions.append({"tool": name, "args": args, "result": result})
                    if "rationale" in result:
                        explanation.append(
                            {
                                "tool": name,
                                "rationale": result["rationale"],
                                "confidence": result.get("confidence"),
                            }
                        )

            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, default=str),
                }
            )

    return (
        "I hit my tool-call limit before finishing. Here's where I got to.",
        actions,
        explanation,
        pending_confirmation,
    )
