"""Diff rendering with real line numbers and syntax highlighting.

A unified diff is dense and easy to misread at a glance, which matters here because the
diff is the main thing standing between "the agent changed something" and "I know what
the agent changed". So: real line numbers from the hunk headers, +/- gutters, and the
code itself highlighted with the right lexer.
"""
from __future__ import annotations

import re
from pathlib import Path

from rich.console import Group
from rich.padding import Padding
from rich.syntax import Syntax
from rich.text import Text

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

# Rich's Syntax wants a lexer name; map by extension and fall back to plain text.
_LEXERS = {
    ".py": "python", ".js": "javascript", ".jsx": "jsx", ".ts": "typescript",
    ".tsx": "tsx", ".rs": "rust", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".rb": "ruby", ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".swift": "swift", ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "scss", ".json": "json",
    ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".md": "markdown",
    ".vue": "vue", ".svelte": "svelte", ".lua": "lua", ".ex": "elixir", ".dart": "dart",
    ".xml": "xml", ".ini": "ini", ".cfg": "ini", ".dockerfile": "docker",
}


def lexer_for(path: str) -> str:
    name = Path(path).name.lower()
    if name in ("dockerfile", "makefile", "rakefile", "gemfile"):
        return {"dockerfile": "docker", "makefile": "make"}.get(name, "text")
    return _LEXERS.get(Path(path).suffix.lower(), "text")


def _highlight(code: str, lexer: str) -> Text:
    """Syntax-highlight one line, returning plain Text if anything goes wrong."""
    if lexer == "text" or not code.strip():
        return Text(code)
    try:
        syntax = Syntax(code, lexer, theme="ansi_dark", background_color="default", word_wrap=False)
        segments = syntax.highlight(code)
        segments.rstrip()
        return segments
    except Exception:
        return Text(code)


def render_diff(console, diff_text: str, max_lines: int = 80, path: str = "") -> None:
    """Pretty-print a unified diff with line numbers and highlighting."""
    if not diff_text or not diff_text.strip():
        return

    lines = diff_text.splitlines()
    if not path:
        for line in lines[:4]:
            if line.startswith("+++ "):
                path = line[4:].strip()
                break
    lexer = lexer_for(path)

    rendered = []
    old_ln = new_ln = 0
    shown = 0
    added = removed = 0

    for line in lines:
        if line.startswith(("--- ", "+++ ", "diff --git", "index ", "new file", "deleted file")):
            continue

        hunk = _HUNK_RE.match(line)
        if hunk:
            old_ln, new_ln = int(hunk.group(1)), int(hunk.group(3))
            ctx = (hunk.group(5) or "").strip()
            label = Text("     ⋮ ", style="diff.gutter") + Text(ctx or "…", style="diff.hunk")
            rendered.append(label)
            continue

        if shown >= max_lines:
            remaining = sum(1 for rest in lines[lines.index(line):] if rest[:1] in "+- ")
            rendered.append(Text(f"     … {remaining} more diff lines", style="dim"))
            break

        kind, code = line[:1], line[1:]
        if kind == "+":
            added += 1
            gutter = Text(f"{new_ln:>5} ", style="diff.gutter.add")
            body = Text("+", style="diff.add.mark") + _highlight(code, lexer)
            rendered.append(gutter + body)
            new_ln += 1
        elif kind == "-":
            removed += 1
            gutter = Text(f"{old_ln:>5} ", style="diff.gutter.remove")
            body = Text("-", style="diff.remove.mark") + Text(code, style="diff.remove")
            rendered.append(gutter + body)
            old_ln += 1
        elif kind == "\\":
            continue
        else:
            gutter = Text(f"{new_ln:>5} ", style="diff.gutter")
            rendered.append(gutter + Text(" ", style="dim") + Text(code, style="diff.context"))
            old_ln += 1
            new_ln += 1
        shown += 1

    if not rendered:
        return

    summary = Text()
    if added:
        summary.append(f"+{added} ", style="diff.add.mark")
    if removed:
        summary.append(f"-{removed}", style="diff.remove.mark")
    if summary.plain.strip():
        rendered.append(Text("     ", style="dim") + summary)

    console.print(Padding(Group(*rendered), (0, 0, 0, 2)))


def diff_stats(diff_text: str) -> tuple:
    """(added, removed) line counts, for compact one-line summaries."""
    added = removed = 0
    for line in (diff_text or "").splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed
