"""Tests for the engine's textual-tool-call recovery (small-local-model
failure mode: the model writes the tool call as JSON text in its reply)."""

from app.agent_engine import parse_textual_tool_call


class TestParseTextualToolCall:
    def test_plain_reply_returns_none(self):
        assert parse_textual_tool_call("The critical path ends 2026-08-06.") is None
        assert parse_textual_tool_call(None) is None
        assert parse_textual_tool_call("") is None

    def test_recovers_simple_call(self):
        # exact shape observed live from llama3.1:8b
        content = (
            "To get the task IDs for Priya's pending tasks, I'll call `get_tasks`.\n\n"
            '{"name": "get_tasks", "parameters": {"assigned_to": 2, "status": "pending"}}'
        )
        name, args = parse_textual_tool_call(content)
        assert name == "get_tasks"
        assert args == {"assigned_to": 2, "status": "pending"}

    def test_recovers_string_encoded_nested_json(self):
        # observed live: perturbations passed as a JSON *string*
        content = (
            "Let me try that again.\n\n"
            '{"name": "run_simulation", "parameters": {"perturbations":'
            '"[{\\"type\\": \\"leave\\", \\"user_id\\": 3, '
            '\\"start_date\\": \\"2026-08-03\\", \\"end_date\\": \\"2026-08-07\\"}]"}}'
        )
        name, args = parse_textual_tool_call(content)
        assert name == "run_simulation"
        assert args["perturbations"] == [
            {"type": "leave", "user_id": 3, "start_date": "2026-08-03", "end_date": "2026-08-07"}
        ]

    def test_accepts_arguments_key(self):
        content = '{"name": "get_projects", "arguments": {}}'
        name, args = parse_textual_tool_call(content)
        assert name == "get_projects"
        assert args == {}

    def test_unknown_tool_returns_none(self):
        assert parse_textual_tool_call('{"name": "rm_rf_slash", "parameters": {}}') is None

    def test_name_in_ordinary_json_data_not_treated_as_call(self):
        # a reply quoting data that merely contains a "name" key
        content = 'Here is the tester: {"name": "Priya Sharma", "id": 2}. Anything else?'
        assert parse_textual_tool_call(content) is None

    def test_invalid_json_ignored(self):
        assert parse_textual_tool_call('{"name": "get_tasks", "parameters": {broken}') is None

    def test_recovers_bare_python_style_call(self):
        # observed live: "Here's the corrected tool call:\n```\nget_workload_summary()\n```"
        content = "Here's the corrected tool call:\n```\nget_workload_summary()\n```"
        name, args = parse_textual_tool_call(content)
        assert name == "get_workload_summary"
        assert args == {}

    def test_recovers_python_style_call_with_json_args(self):
        content = 'I will run get_tasks({"status": "pending"}) now.'
        name, args = parse_textual_tool_call(content)
        assert name == "get_tasks"
        assert args == {"status": "pending"}
