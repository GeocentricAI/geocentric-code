"""Filesystem tools: read, write, edit, multi-edit, list."""
from __future__ import annotations

import difflib
import os
from pathlib import Path

from .. import platform_compat as pc
from ..context import FileRegistry
from .base import ToolResult

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".geocentric",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", ".next",
    ".turbo", "target", ".gradle", ".idea", ".DS_Store", "coverage", ".tox",
}

MAX_READ_BYTES = 512_000
BINARY_SNIFF_BYTES = 8_000

# Shared with the agent so edits can tell "you read this file" from "you're editing a
# file you've never looked at", and catch files that changed underneath us.
REGISTRY = FileRegistry()


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _read_text(p: Path, *, lossy: bool = False):
    """Returns (text, error_message). UTF-8 + newline="" everywhere: Windows' locale
    codepage can't round-trip arbitrary source files, and without newline="" both
    read_text and write_text translate line endings, silently flipping an LF file to
    CRLF the moment a single line in it changes.

    `lossy=True` (errors="replace") is only for text that gets *displayed*, never text
    that might later be written back - replacing an undecodable byte with U+FFFD is a
    one-way trip, and doing that to something we then write to disk would permanently
    corrupt whatever was really there.
    """
    # Path.read_text()/write_text() don't accept newline= until Python 3.10 (this
    # project targets 3.9+); the built-in open() has supported it since forever, so we
    # go through that instead of the pathlib convenience methods.
    try:
        with p.open("r", encoding=pc.TEXT_ENCODING, newline=pc.TEXT_NEWLINE,
                   errors="replace" if lossy else "strict") as f:
            return f.read(), None
    except UnicodeDecodeError:
        return None, f"{p} isn't valid UTF-8 (looks like a different encoding, or a binary file)."
    except OSError as e:
        return None, f"Could not read {p}: {e}"


def _write_text(p: Path, text: str):
    """Returns an error message, or None on success."""
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding=pc.TEXT_ENCODING, newline=pc.TEXT_NEWLINE) as f:
            f.write(text)
        return None
    except OSError as e:
        return f"Could not write {p}: {e}"


def _looks_binary(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            chunk = f.read(BINARY_SNIFF_BYTES)
    except OSError:
        return False
    if b"\x00" in chunk:
        return True
    # Mostly-unprintable content is binary for our purposes.
    if not chunk:
        return False
    printable = sum(1 for b in chunk if 32 <= b < 127 or b in (9, 10, 13))
    return printable / len(chunk) < 0.7


def read_file(path: str, start_line: int = None, end_line: int = None):
    p = _resolve(path)
    if not p.exists():
        # A wrong-path guess is the single most common tool failure; a nudge toward
        # the right neighbourhood saves a whole round-trip.
        hint = ""
        parent = p.parent
        if parent.is_dir():
            near = [c.name for c in parent.iterdir() if c.name.lower().startswith(p.name[:3].lower())][:5]
            if near:
                hint = f" Did you mean one of: {', '.join(near)}?"
        return ToolResult(ok=False, error=f"No such file: {p}.{hint}")
    if p.is_dir():
        return ToolResult(ok=False, error=f"{p} is a directory - use list_dir instead")
    if _looks_binary(p):
        size = p.stat().st_size
        return ToolResult(ok=False, error=f"{p} appears to be a binary file ({size:,} bytes); not reading it as text")

    try:
        size = p.stat().st_size
        if size > MAX_READ_BYTES and not (start_line or end_line):
            return ToolResult(
                ok=False,
                error=(
                    f"{p} is {size:,} bytes, too large to read at once. "
                    f"Pass start_line/end_line to page through it, or grep for what you need."
                ),
            )
    except OSError as e:
        return ToolResult(ok=False, error=f"Could not read {p}: {e}")

    text, err = _read_text(p, lossy=True)
    if err:
        return ToolResult(ok=False, error=err)

    lines = text.splitlines()
    start = max(1, start_line or 1)
    end = min(len(lines), end_line or len(lines))
    if start > len(lines):
        return ToolResult(ok=False, error=f"{p} has only {len(lines)} lines; start_line={start} is past the end")

    numbered = [f"{i:>6}\t{lines[i - 1]}" for i in range(start, end + 1)]
    body = "\n".join(numbered) if numbered else "(empty file)"
    if end < len(lines):
        body += f"\n... ({len(lines) - end:,} more lines; total {len(lines):,})"

    REGISTRY.record(p)
    return ToolResult(ok=True, output=body, meta={"path": str(p), "total_lines": len(lines)})


def write_file(path: str, content: str):
    p = _resolve(path)
    existed = p.exists()
    old_text = ""
    old_text_valid = True
    if existed:
        if p.is_dir():
            return ToolResult(ok=False, error=f"{p} is a directory, not a file")
        # write_file replaces the file wholesale, so an old_text decode failure doesn't
        # block the write - but we mustn't offer /undo based on a lossy read, since
        # restoring "old_text" would permanently stamp U+FFFD over whatever was really
        # there. Skip recording old_text (below) if we can't be sure it's exact.
        text, err = _read_text(p, lossy=True)
        old_text = text or ""
        old_text_valid = err is None
        if old_text_valid and old_text == content:
            return ToolResult(ok=True, output=f"{p} already had exactly this content; nothing to do",
                              meta={"path": str(p), "noop": True})

    diff = "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=str(p) if existed else pc.devnull(),
            tofile=str(p),
            n=3,
        )
    )

    err = _write_text(p, content)
    if err:
        return ToolResult(ok=False, error=err)

    REGISTRY.record(p)
    action = "updated" if existed else "created"
    meta = {"path": str(p), "existed": existed}
    if old_text_valid:
        meta["old_text"] = old_text  # enables /undo; omitted when the prior content was lossy
    return ToolResult(
        ok=True,
        output=f"{action} {p} ({len(content.splitlines()):,} lines)",
        diff=diff or None,
        meta=meta,
    )


def _stale_check(p: Path):
    if REGISTRY.changed_since_read(p):
        return ToolResult(
            ok=False,
            error=(
                f"{p} changed on disk since it was last read (edited outside geocentric?). "
                f"Re-read it before editing so the change isn't clobbered."
            ),
        )
    return None


def _apply_one_edit(text: str, old_string: str, new_string: str, replace_all: bool):
    """Returns (new_text, error)."""
    if old_string == "":
        return None, "old_string must not be empty"
    if old_string == new_string:
        return None, "old_string and new_string are identical"
    count = text.count(old_string)
    if count == 0:
        return None, "old_string not found in file"
    if count > 1 and not replace_all:
        return None, (
            f"old_string appears {count} times; it must be unique. "
            f"Include surrounding context to disambiguate, or pass replace_all=true."
        )
    return (text.replace(old_string, new_string) if replace_all
            else text.replace(old_string, new_string, 1)), None


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False):
    p = _resolve(path)
    if not p.exists():
        return ToolResult(ok=False, error=f"No such file: {p}")
    stale = _stale_check(p)
    if stale:
        return stale
    text, err = _read_text(p)
    if err:
        return ToolResult(ok=False, error=err)

    new_text, err = _apply_one_edit(text, old_string, new_string, replace_all)
    if err:
        return ToolResult(ok=False, error=err)

    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True), new_text.splitlines(keepends=True),
            fromfile=str(p), tofile=str(p), n=3,
        )
    )
    err = _write_text(p, new_text)
    if err:
        return ToolResult(ok=False, error=err)

    REGISTRY.record(p)
    n = text.count(old_string) if replace_all else 1
    return ToolResult(
        ok=True,
        output=f"edited {p} ({n} replacement{'s' if n != 1 else ''})",
        diff=diff or None,
        meta={"path": str(p), "old_text": text, "existed": True},
    )


def multi_edit(path: str, edits: list):
    """Apply several edits to one file atomically.

    Sequential edit_file calls on the same file are both slow (a round-trip each) and
    fragile - a later edit can fail after earlier ones already landed, leaving the file
    half-changed. Here every edit is applied to an in-memory copy first and the file is
    only written if all of them succeed.
    """
    p = _resolve(path)
    if not p.exists():
        return ToolResult(ok=False, error=f"No such file: {p}")
    if not isinstance(edits, list) or not edits:
        return ToolResult(ok=False, error="'edits' must be a non-empty list of {old_string, new_string} objects")
    stale = _stale_check(p)
    if stale:
        return stale
    original, err = _read_text(p)
    if err:
        return ToolResult(ok=False, error=err)

    text = original
    for i, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            return ToolResult(ok=False, error=f"edit #{i} is not an object")
        text, err = _apply_one_edit(
            text,
            edit.get("old_string", ""),
            edit.get("new_string", ""),
            bool(edit.get("replace_all", False)),
        )
        if err:
            return ToolResult(ok=False, error=f"edit #{i} failed: {err} (no changes were written)")

    diff = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True), text.splitlines(keepends=True),
            fromfile=str(p), tofile=str(p), n=3,
        )
    )
    err = _write_text(p, text)
    if err:
        return ToolResult(ok=False, error=err)

    REGISTRY.record(p)
    return ToolResult(
        ok=True,
        output=f"applied {len(edits)} edits to {p}",
        diff=diff or None,
        meta={"path": str(p), "old_text": original, "existed": True},
    )


def list_dir(path: str = ".", recursive: bool = False, max_entries: int = 300):
    p = _resolve(path)
    if not p.exists():
        return ToolResult(ok=False, error=f"No such path: {p}")
    if not p.is_dir():
        return ToolResult(ok=False, error=f"{p} is not a directory")

    entries = []
    if recursive:
        for root, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not d.startswith("."))
            rel_root = os.path.relpath(root, p)
            # Always display forward slashes, even on Windows: the model reads these
            # paths back and often echoes them into later tool calls, and a mix of
            # os.sep and "/" (from the manually-appended trailing slash below) is
            # needlessly confusing either way.
            prefix = "" if rel_root == "." else rel_root.replace(os.sep, "/") + "/"
            for d in dirs:
                entries.append(f"{prefix}{d}/")
            for f in sorted(files):
                if f.startswith("."):
                    continue
                entries.append(f"{prefix}{f}")
            if len(entries) >= max_entries:
                break
    else:
        try:
            for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if e.name in IGNORE_DIRS:
                    continue
                entries.append(e.name + "/" if e.is_dir() else e.name)
        except OSError as e:
            return ToolResult(ok=False, error=f"Could not list {p}: {e}")

    truncated = len(entries) > max_entries
    entries = entries[:max_entries]
    body = "\n".join(entries) if entries else "(empty directory)"
    if truncated:
        body += f"\n... truncated at {max_entries} entries"
    return ToolResult(ok=True, output=body, meta={"path": str(p), "count": len(entries)})
