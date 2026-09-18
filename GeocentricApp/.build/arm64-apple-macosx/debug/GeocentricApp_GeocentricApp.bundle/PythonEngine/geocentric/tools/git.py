"""Git tools: status, diff, log, branch, show, commit."""
from __future__ import annotations

from .base import ToolResult, truncate_output
from .shell import _run


def _git(args: list, cwd: str = ".", timeout: int = 30):
    result = _run(["git", "-C", cwd] + args, timeout=timeout)
    if not result.ok and "not a git repository" in (result.error or "").lower():
        return ToolResult(ok=False, error="This directory isn't a git repository.")
    return result


def status(path: str = "."):
    result = _git(["status", "--porcelain=v1", "-b"], cwd=path)
    if result.ok and not result.output.strip():
        return ToolResult(ok=True, output="working tree clean")
    return result


def diff(path: str = ".", staged: bool = False, target: str = None):
    args = ["diff"]
    if staged:
        args.append("--cached")
    if target:
        args.append(target)
    result = _git(args, cwd=path, timeout=45)
    if result.ok and not result.output.strip():
        return ToolResult(ok=True, output="(no changes)")
    if result.ok:
        result.output = truncate_output(result.output, limit=20_000)
    return result


def log(path: str = ".", max_count: int = 10, file: str = None):
    args = ["log", f"-{max_count}", "--pretty=format:%h %ad %an: %s", "--date=short"]
    if file:
        args += ["--", file]
    return _git(args, cwd=path)


def branch(path: str = "."):
    return _git(["branch", "-vv", "--all"], cwd=path)


def show(ref: str, path: str = "."):
    result = _git(["show", "--stat", "--patch", ref], cwd=path, timeout=45)
    if result.ok:
        result.output = truncate_output(result.output, limit=20_000)
    return result


def commit(message: str, paths: list = None, path: str = "."):
    if not message or not message.strip():
        return ToolResult(ok=False, error="A commit message is required.")

    add_result = _git(["add"] + (list(paths) if paths else ["-A"]), cwd=path)
    if not add_result.ok:
        return add_result

    staged = _git(["diff", "--cached", "--name-only"], cwd=path)
    if staged.ok and not staged.output.strip():
        return ToolResult(ok=False, error="Nothing staged to commit.")

    result = _git(["commit", "-m", message], cwd=path)
    if result.ok:
        head = _git(["log", "-1", "--pretty=format:%h %s"], cwd=path)
        if head.ok:
            result.output = f"committed {head.output}"
    return result
