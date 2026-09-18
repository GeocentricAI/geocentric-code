"""Translates Geocentric's real, structured tool events into the inline
pseudo-XML tag vocabulary the bundled web chat frontend (web/index.html)
already knows how to parse for its activity checklist and terminal panel -
see parseActivities() / stripInternalTagsJS() there.

Nothing here executes anything or makes safety decisions; geocentric's own
Agent/tools/safety machinery (run as a gui_bridge.py subprocess) already did
that before these events ever reach us. This module only formats text.

Two gotchas baked in on purpose, both discovered by reading the frontend:
  - `write_file`/`edit_file`/`read_file`/`delete_file`/`run_file` are dropped
    entirely by the frontend's parser unless they carry a filename/file/path
    attribute - so every file tag below always gets `filename="..."`.
  - `run_command`/`run_bg_command`/`agent_terminal` with NO attributes and a
    body that doesn't start with "\n" are treated as an incidental mention of
    the word and silently skipped - so every shell tag below always carries a
    `command="..."` attribute too, not just a body.
"""
from __future__ import annotations

import html


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _attr(name: str, value) -> str:
    return f'{name}="{esc(value)}"'


def open_tag(tag: str, **attrs) -> str:
    attr_str = "".join(f" {_attr(k, v)}" for k, v in attrs.items() if v is not None)
    return f"<{tag}{attr_str}>"


def close_tag(tag: str) -> str:
    return f"</{tag}>"


def self_closed(tag: str, **attrs) -> str:
    attr_str = "".join(f" {_attr(k, v)}" for k, v in attrs.items() if v is not None)
    return f"<{tag}{attr_str} />"


# tool name -> (tag, attr-builder(args) -> dict, body-builder(args) -> str|None)
def _first_line(text: str, limit: int = 200) -> str:
    return (text or "").strip().split("\n", 1)[0][:limit]


_TOOL_MAP = {
    "read_file": ("read_file", lambda a: {"filename": a.get("path", "")}, lambda a: None),
    "write_file": ("write_file", lambda a: {"filename": a.get("path", "")}, lambda a: None),
    "edit_file": ("edit_file", lambda a: {"filename": a.get("path", "")}, lambda a: None),
    "multi_edit": ("edit_file", lambda a: {"filename": a.get("path", "")}, lambda a: None),
    "list_dir": ("view_project_tree", lambda a: {}, lambda a: None),
    "project_overview": ("view_project_tree", lambda a: {}, lambda a: None),
    "glob_files": ("search_code", lambda a: {"query": a.get("pattern", "")}, lambda a: None),
    "grep": ("search_code", lambda a: {"query": a.get("pattern", "")}, lambda a: None),
    "run_command": ("run_command", lambda a: {"command": _first_line(a.get("command", ""))},
                     lambda a: a.get("command", "")),
    "run_python": ("run_command", lambda a: {"command": _first_line(a.get("code", "")) or "python snippet"},
                    lambda a: a.get("code", "")),
    "check_job": ("list_processes", lambda a: {}, lambda a: None),
    "list_jobs": ("list_processes", lambda a: {}, lambda a: None),
    "kill_job": ("kill_process", lambda a: {"pid": a.get("job_id", "")}, lambda a: None),
    "fetch_url": ("browse_url", lambda a: {"url": a.get("url", "")}, lambda a: None),
    "git_status": ("git_status", lambda a: {}, lambda a: None),
    "git_diff": ("git_diff", lambda a: {}, lambda a: None),
    "git_branch": ("git_branch", lambda a: {}, lambda a: None),
    "git_commit": ("git_commit", lambda a: {"message": _first_line(a.get("message", ""))}, lambda a: None),
}

# Tools with no matching UI concept in the frontend at all - rendered as a
# generic status line, which parseActivities already handles for any label.
_STATUS_ONLY = {
    "delegate_to_peer": lambda a: f"Delegating to a peer machine: {_first_line(a.get('task', ''))}",
    "git_log": lambda a: "Checking Git log",
    "git_show": lambda a: f"Inspecting commit {a.get('ref', 'HEAD')}",
    "set_context_window": lambda a: "Adjusting context window",
}


def tool_call_open(name: str, args: dict) -> str:
    """Text to append to a job's progress log the moment a tool call starts."""
    if name == "web_search":
        return open_tag("search") + esc(args.get("query", ""))
    if name in _TOOL_MAP:
        tag, attr_fn, body_fn = _TOOL_MAP[name]
        body = body_fn(args)
        opening = open_tag(tag, **attr_fn(args))
        return opening + ("\n" + esc(body) if body else "")
    if name in _STATUS_ONLY:
        return open_tag("status") + esc(_STATUS_ONLY[name](args)) + close_tag("status")
    return open_tag("status") + esc(f"Running {name}") + close_tag("status")


def tool_call_close(name: str) -> str:
    """Text to append once that same tool call's result has arrived. Empty
    for tags that were already self-contained (status lines, web search)."""
    if name == "web_search":
        return close_tag("search")
    if name in _TOOL_MAP:
        tag, _, _ = _TOOL_MAP[name]
        return close_tag(tag)
    return ""


def question_block(question: str, options: list) -> str:
    """Formats an ask_user question as the frontend's native `Q:`/`A:` choice-card
    convention (see parseQABlocks/injectQAChoices in web/index.html) instead of
    inventing new frontend UI. Clicking a choice resubmits its title as the next
    chat message; bridge.py's per-session pending-question flag routes that
    message back to gui_bridge as an answer instead of a fresh prompt.
    """
    lines = [f"Q: {question}"]
    for opt in options:
        label = opt.get("label", opt) if isinstance(opt, dict) else opt
        desc = opt.get("description", "") if isinstance(opt, dict) else ""
        lines.append(f"A: {label} | {desc}" if desc else f"A: {label}")
    return "\n" + "\n".join(lines) + "\n"


def roadmap_tag() -> str:
    """Geocentric emits a distinct `todo_update` event (not a tool_call/tool_result
    pair) whenever the agent's task list changes - it's a single atomic snapshot,
    not a call with a separate result, so it only ever needs the self-closed form."""
    return self_closed("update_roadmap")
