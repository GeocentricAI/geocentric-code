"""Tool registry: JSON-schema definitions + dispatch for the agent's function calls."""
from __future__ import annotations

from typing import Optional

from . import fs, git as git_tools, interact, peer, search, settings, shell, todo, web
from .base import ToolResult, ToolSpec, truncate_output

__all__ = ["ToolResult", "ToolSpec", "truncate_output", "TOOLS", "get_tool", "all_specs", "as_ollama_tools"]

TOOLS: dict = {}


def _register(spec: ToolSpec) -> None:
    TOOLS[spec.name] = spec


# ---------------------------------------------------------------- reading & searching

_register(ToolSpec(
    name="read_file",
    description=(
        "Read a text file. Returns content with 1-indexed line numbers. Use start_line/end_line "
        "to page through large files. Always read a file before editing it."
    ),
    parameters={
        "path": {"type": "string", "description": "File path, absolute or relative to the cwd."},
        "start_line": {"type": "integer", "description": "1-indexed first line to read (optional)."},
        "end_line": {"type": "integer", "description": "1-indexed last line to read, inclusive (optional)."},
    },
    required=["path"],
    fn=fs.read_file,
    mutating=False,
    concurrent_safe=True,
    group="read",
))

_register(ToolSpec(
    name="list_dir",
    description="List files and directories under a path, skipping noise like .git and node_modules.",
    parameters={
        "path": {"type": "string", "description": "Directory path. Defaults to the current directory."},
        "recursive": {"type": "boolean", "description": "Recurse into subdirectories. Default false."},
        "max_entries": {"type": "integer", "description": "Cap on entries returned. Default 300."},
    },
    required=[],
    fn=fs.list_dir,
    mutating=False,
    concurrent_safe=True,
    group="read",
))

_register(ToolSpec(
    name="grep",
    description=(
        "Search file contents by regex across the project (ripgrep-backed when available). "
        "This is the fastest way to find where something is defined or used."
    ),
    parameters={
        "pattern": {"type": "string", "description": "Regex pattern to search for."},
        "path": {"type": "string", "description": "Directory or file to search. Defaults to cwd."},
        "glob": {"type": "string", "description": "Only search files matching this glob, e.g. '*.py'."},
        "case_insensitive": {"type": "boolean", "description": "Case-insensitive search. Default false."},
        "max_results": {"type": "integer", "description": "Cap on matches. Default 200."},
        "context": {"type": "integer", "description": "Lines of surrounding context per match. Default 0."},
    },
    required=["pattern"],
    fn=search.grep,
    mutating=False,
    concurrent_safe=True,
    group="read",
))

_register(ToolSpec(
    name="glob_files",
    description="Find files by name pattern, e.g. '**/*.test.ts'. Use when you know the filename shape but not the location.",
    parameters={
        "pattern": {"type": "string", "description": "Glob pattern."},
        "path": {"type": "string", "description": "Base directory. Defaults to cwd."},
    },
    required=["pattern"],
    fn=search.glob_files,
    mutating=False,
    concurrent_safe=True,
    group="read",
))

_register(ToolSpec(
    name="project_overview",
    description=(
        "Summarize the project: languages, manifests, top-level layout, README excerpt. "
        "Cheap orientation - run this first in an unfamiliar codebase."
    ),
    parameters={"path": {"type": "string", "description": "Project root. Defaults to cwd."}},
    required=[],
    fn=search.project_overview,
    mutating=False,
    concurrent_safe=True,
    group="read",
))

_register(ToolSpec(
    name="web_search",
    description=(
        "Search the web (DuckDuckGo, no API key) and get back titles, URLs, and snippets. "
        "Use this for anything not already on disk or in your training data - current "
        "events, a library's real API, an error message you don't recognize. Follow up "
        "with fetch_url on a promising result to read the actual page."
    ),
    parameters={
        "query": {"type": "string", "description": "The search query."},
        "max_results": {"type": "integer", "description": "Cap on results returned. Default 8."},
    },
    required=["query"],
    fn=web.web_search,
    mutating=False,
    concurrent_safe=True,
    group="web",
))

_register(ToolSpec(
    name="fetch_url",
    description=(
        "Fetch a web page and return its readable text (HTML stripped). Use this to read "
        "a page found via web_search, check documentation, or pull the contents of a URL "
        "the user gave you."
    ),
    parameters={
        "url": {"type": "string", "description": "The URL to fetch (http:// or https://)."},
        "max_chars": {"type": "integer", "description": "Cap on characters returned. Default 8000."},
    },
    required=["url"],
    fn=web.fetch_url,
    mutating=False,
    concurrent_safe=True,
    group="web",
))

_register(ToolSpec(
    name="delegate_to_peer",
    description=(
        "Hand a self-contained sub-task to the paired Mac's own agent, so it runs on its "
        "own model at the same time you keep working. Only available in orchestration mode "
        "(two Macs linked and paired, each running its own model - see the Machines settings "
        "panel). The peer works read-only right now: it can investigate, analyze, or draft "
        "text, but not write files - fold its answer into your own work rather than trusting "
        "it blindly. State the task fully; the peer has no memory of this conversation."
    ),
    parameters={
        "task": {"type": "string", "description": "A self-contained description of the sub-task for the peer to do."},
    },
    required=["task"],
    fn=peer.delegate_to_peer,
    mutating=False,
    concurrent_safe=True,
    group="peer",
))

# ---------------------------------------------------------------------------- editing

_register(ToolSpec(
    name="write_file",
    description=(
        "Create a new file, or completely replace an existing one. For changes to an existing "
        "file prefer edit_file or multi_edit - a full rewrite risks losing content you didn't read."
    ),
    parameters={
        "path": {"type": "string", "description": "File path to write."},
        "content": {"type": "string", "description": "Full text content of the file."},
    },
    required=["path", "content"],
    fn=fs.write_file,
    mutating=True,
    danger="medium",
    group="edit",
))

_register(ToolSpec(
    name="edit_file",
    description=(
        "Replace an exact string in a file. old_string must appear exactly once unless "
        "replace_all is true - include surrounding lines to make it unique."
    ),
    parameters={
        "path": {"type": "string", "description": "File path to edit."},
        "old_string": {"type": "string", "description": "Exact text to find, including indentation."},
        "new_string": {"type": "string", "description": "Text to replace it with."},
        "replace_all": {"type": "boolean", "description": "Replace every occurrence. Default false."},
    },
    required=["path", "old_string", "new_string"],
    fn=fs.edit_file,
    mutating=True,
    danger="medium",
    group="edit",
))

_register(ToolSpec(
    name="multi_edit",
    description=(
        "Apply several edits to one file in a single atomic operation. Edits apply in order; "
        "if any one fails nothing is written. Prefer this over repeated edit_file calls on the same file."
    ),
    parameters={
        "path": {"type": "string", "description": "File path to edit."},
        "edits": {
            "type": "array",
            "description": "List of {old_string, new_string, replace_all?} objects, applied in order.",
            "items": {
                "type": "object",
                "properties": {
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                    "replace_all": {"type": "boolean"},
                },
                "required": ["old_string", "new_string"],
            },
        },
    },
    required=["path", "edits"],
    fn=fs.multi_edit,
    mutating=True,
    danger="medium",
    group="edit",
))

# --------------------------------------------------------------------------- shell/run

_register(ToolSpec(
    name="run_command",
    description=(
        "Run a shell command (build, test, lint, package managers, anything). "
        "Set background=true for long-running processes like dev servers so they don't block."
    ),
    parameters={
        "command": {"type": "string", "description": "The shell command to run."},
        "cwd": {"type": "string", "description": "Working directory. Defaults to the current directory."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 120."},
        "background": {"type": "boolean", "description": "Run detached and return a job id. Default false."},
    },
    required=["command"],
    fn=shell.run_command,
    mutating=True,
    danger="high",
    group="shell",
))

_register(ToolSpec(
    name="run_python",
    description="Run a snippet of Python in a subprocess. Good for quick calculations or one-off scripts.",
    parameters={
        "code": {"type": "string", "description": "Python source code to execute."},
        "timeout": {"type": "integer", "description": "Timeout in seconds. Default 60."},
    },
    required=["code"],
    fn=shell.run_python,
    mutating=True,
    danger="high",
    group="shell",
))

_register(ToolSpec(
    name="check_job",
    description="Read the latest output from a background job started with run_command(background=true).",
    parameters={
        "job_id": {"type": "string", "description": "The job id, e.g. 'job1'."},
        "tail": {"type": "integer", "description": "How many trailing lines to show. Default 60."},
    },
    required=["job_id"],
    fn=shell.check_job,
    mutating=False,
    concurrent_safe=True,
    group="shell",
))

_register(ToolSpec(
    name="kill_job",
    description="Stop a background job and its child processes.",
    parameters={"job_id": {"type": "string", "description": "The job id to stop."}},
    required=["job_id"],
    fn=shell.kill_job,
    mutating=True,
    danger="medium",
    group="shell",
))

_register(ToolSpec(
    name="list_jobs",
    description="List background jobs and whether they're still running.",
    parameters={},
    required=[],
    fn=shell.list_jobs,
    mutating=False,
    concurrent_safe=True,
    group="shell",
))

# -------------------------------------------------------------------------------- git

_register(ToolSpec(
    name="git_status",
    description="Show git status and current branch.",
    parameters={"path": {"type": "string", "description": "Repo path. Defaults to cwd."}},
    required=[],
    fn=git_tools.status,
    mutating=False,
    concurrent_safe=True,
    group="git",
))

_register(ToolSpec(
    name="git_diff",
    description="Show a git diff: unstaged by default, staged with staged=true, or against a ref with target.",
    parameters={
        "path": {"type": "string", "description": "Repo path. Defaults to cwd."},
        "staged": {"type": "boolean", "description": "Show the staged diff instead. Default false."},
        "target": {"type": "string", "description": "Diff against a ref/branch, e.g. 'main'."},
    },
    required=[],
    fn=git_tools.diff,
    mutating=False,
    concurrent_safe=True,
    group="git",
))

_register(ToolSpec(
    name="git_log",
    description="Show recent commit history, optionally for one file.",
    parameters={
        "path": {"type": "string", "description": "Repo path. Defaults to cwd."},
        "max_count": {"type": "integer", "description": "Number of commits. Default 10."},
        "file": {"type": "string", "description": "Limit history to this file (optional)."},
    },
    required=[],
    fn=git_tools.log,
    mutating=False,
    concurrent_safe=True,
    group="git",
))

_register(ToolSpec(
    name="git_branch",
    description="List local and remote branches with tracking info.",
    parameters={"path": {"type": "string", "description": "Repo path. Defaults to cwd."}},
    required=[],
    fn=git_tools.branch,
    mutating=False,
    concurrent_safe=True,
    group="git",
))

_register(ToolSpec(
    name="git_show",
    description="Show a specific commit's message, stat, and patch.",
    parameters={
        "ref": {"type": "string", "description": "Commit ref, e.g. 'HEAD~1' or a sha."},
        "path": {"type": "string", "description": "Repo path. Defaults to cwd."},
    },
    required=["ref"],
    fn=git_tools.show,
    mutating=False,
    concurrent_safe=True,
    group="git",
))

_register(ToolSpec(
    name="git_commit",
    description="Stage changes and commit. Omit paths to stage everything.",
    parameters={
        "message": {"type": "string", "description": "Commit message."},
        "paths": {"type": "array", "items": {"type": "string"}, "description": "Paths to stage. Omit for all."},
        "path": {"type": "string", "description": "Repo path. Defaults to cwd."},
    },
    required=["message"],
    fn=git_tools.commit,
    mutating=True,
    danger="medium",
    group="git",
))

# ------------------------------------------------------------------------------ tasks

_register(ToolSpec(
    name="todo_write",
    description=(
        "Record or update your task list for the current request. Call this at the start of any "
        "multi-step task, then again to mark each item completed as you finish it. Exactly one item "
        "may be 'in_progress' at a time. The user sees this list, so keep it accurate."
    ),
    parameters={
        "todos": {
            "type": "array",
            "description": "The full task list, replacing any previous one.",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "What needs doing, imperative."},
                    "status": {"type": "string", "enum": list(todo.VALID_STATUSES)},
                },
                "required": ["content", "status"],
            },
        }
    },
    required=["todos"],
    fn=todo.todo_write,
    mutating=False,  # touches no user data; gating it behind approval would be pure friction
    group="task",
))


_OPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Short choice text."},
        "description": {"type": "string", "description": "One line on what it means."},
    },
    "required": ["label"],
}

_register(ToolSpec(
    name="ask_user",
    description=(
        "Ask the user one or more multiple-choice questions and wait for their answers, with a "
        "real arrow-key picker - not a guess. Use this when the request is genuinely ambiguous "
        "and guessing wrong would waste real work: which library to use, which of two files they "
        "meant, whether to include tests. Offer 2-4 concrete options with short descriptions each. "
        "For a single question use question/options/multi_select; for several related questions in "
        "one go (a short wizard, e.g. gathering a few preferences before starting a task) use "
        "'questions' instead and leave the others unset. Don't use this for things you can "
        "determine yourself by reading the code."
    ),
    parameters={
        "question": {"type": "string", "description": "A single question, phrased clearly and specifically."},
        "options": {
            "type": "array",
            "description": "2-4 concrete choices for 'question'.",
            "items": _OPTION_SCHEMA,
        },
        "multi_select": {"type": "boolean", "description": "Allow choosing several for 'question'. Default false."},
        "questions": {
            "type": "array",
            "description": "Several questions to ask in one wizard, instead of a single 'question'.",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": _OPTION_SCHEMA},
                    "multi_select": {"type": "boolean"},
                },
                "required": ["question", "options"],
            },
        },
    },
    required=[],
    fn=interact.ask_user,
    mutating=False,
    group="task",
))

_register(ToolSpec(
    name="set_context_window",
    description=(
        "Change how many tokens of context are requested from Ollama, or reset to automatic. "
        "Raise it if you're running out of room on a long task; note that a larger window uses "
        "more GPU memory."
    ),
    parameters={
        "tokens": {"type": "integer", "description": "New window size in tokens, e.g. 32768."},
        "reset": {"type": "boolean", "description": "Reset to the automatic default instead."},
    },
    required=[],
    fn=settings.set_context_window,
    mutating=True,
    danger="low",
    group="task",
))


def get_tool(name: str) -> Optional[ToolSpec]:
    return TOOLS.get(name)


def all_specs() -> list:
    return list(TOOLS.values())


def as_ollama_tools(names: Optional[list] = None) -> list:
    specs = TOOLS.values() if names is None else [TOOLS[n] for n in names if n in TOOLS]
    return [spec.as_ollama_tool() for spec in specs]


def read_only_names() -> list:
    return [s.name for s in TOOLS.values() if not s.mutating]
