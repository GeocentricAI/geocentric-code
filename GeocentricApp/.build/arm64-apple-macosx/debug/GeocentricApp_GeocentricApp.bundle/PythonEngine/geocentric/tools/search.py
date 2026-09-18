"""Search tools: grep (ripgrep-backed when available), glob, and a project overview."""
from __future__ import annotations

import fnmatch
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

from .. import platform_compat as pc
from .base import ToolResult, truncate_output
from .fs import IGNORE_DIRS

_RG = shutil.which("rg")

# rg's output is "path:line:content". Splitting on the first ":" breaks the instant a
# Windows absolute path is involved - "C:\proj\file.py:12:text".split(":", 1) yields
# "C", not the path. Match "path:linenum:" instead; greedy `.+` correctly consumes up to
# the *last* :digits: before the content in the (rare) case the content itself contains
# something colon-number-shaped.
_RG_MATCH_RE = re.compile(r"^(.+):(\d+):")

# Extensions worth counting in a project overview; everything else is noise.
_CODE_EXTS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".kt", ".rb", ".php",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".swift", ".m", ".scala", ".sh", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte", ".lua", ".ex", ".exs", ".dart",
}

_MANIFESTS = [
    "package.json", "pyproject.toml", "setup.py", "requirements.txt", "Cargo.toml",
    "go.mod", "pom.xml", "build.gradle", "Gemfile", "composer.json", "Makefile",
    "Dockerfile", "docker-compose.yml", "tsconfig.json", ".python-version",
]


def grep(
    pattern: str,
    path: str = ".",
    glob: str = None,
    case_insensitive: bool = False,
    max_results: int = 200,
    context: int = 0,
):
    base = Path(path).expanduser().resolve()
    if not base.exists():
        return ToolResult(ok=False, error=f"No such path: {base}")
    if _RG:
        return _grep_rg(pattern, base, glob, case_insensitive, max_results, context)
    return _grep_python(pattern, base, glob, case_insensitive, max_results)


def _grep_rg(pattern, base: Path, glob, case_insensitive, max_results, context):
    cmd = ["rg", "--line-number", "--no-heading", "--color", "never", "-m", str(max(1, max_results // 4))]
    if case_insensitive:
        cmd.append("-i")
    if context:
        cmd += ["-C", str(min(context, 10))]
    if glob:
        cmd += ["-g", glob]
    for d in ("node_modules", ".git", "dist", "build", ".venv", "__pycache__"):
        cmd += ["-g", f"!{d}"]
    cmd += ["--", pattern, str(base)]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30, **pc.SUBPROCESS_TEXT_KWARGS)
    except subprocess.TimeoutExpired:
        return ToolResult(ok=False, error="grep timed out")
    except Exception as e:
        return ToolResult(ok=False, error=f"ripgrep failed: {e}")

    if proc.returncode not in (0, 1):
        return ToolResult(ok=False, error=proc.stderr.strip() or "ripgrep failed")

    lines = proc.stdout.splitlines()[:max_results]
    if not lines:
        return ToolResult(ok=True, output="(no matches)", meta={"engine": "ripgrep", "count": 0})

    def _match_path(line: str) -> str:
        m = _RG_MATCH_RE.match(line)
        return m.group(1) if m else line.split(":", 1)[0]

    files = len({_match_path(ln) for ln in lines})
    body = truncate_output("\n".join(lines))
    return ToolResult(
        ok=True,
        output=f"{len(lines)} matches in {files} files:\n{body}",
        meta={"engine": "ripgrep", "count": len(lines)},
    )


def _grep_python(pattern, base: Path, glob, case_insensitive, max_results):
    try:
        regex = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
    except re.error as e:
        return ToolResult(ok=False, error=f"Invalid regex: {e}")

    matches = []
    paths = [base] if base.is_file() else base.rglob("*")
    for f in paths:
        if len(matches) >= max_results:
            break
        if f.is_dir() or any(part in IGNORE_DIRS for part in f.parts):
            continue
        if glob and not fnmatch.fnmatch(f.name, glob):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append(f"{f}:{i}:{line.strip()[:300]}")
                if len(matches) >= max_results:
                    break

    if not matches:
        return ToolResult(ok=True, output="(no matches)", meta={"engine": "python", "count": 0})
    return ToolResult(
        ok=True,
        output=f"{len(matches)} matches:\n" + truncate_output("\n".join(matches)),
        meta={"engine": "python", "count": len(matches)},
    )


def glob_files(pattern: str, path: str = "."):
    base = Path(path).expanduser().resolve()
    if not base.exists():
        return ToolResult(ok=False, error=f"No such path: {base}")

    results = []
    try:
        for f in base.glob(pattern):
            if any(part in IGNORE_DIRS for part in f.parts):
                continue
            try:
                results.append(str(f.relative_to(base)))
            except ValueError:
                results.append(str(f))
            if len(results) >= 500:
                break
    except (OSError, ValueError) as e:
        return ToolResult(ok=False, error=f"Bad glob pattern: {e}")

    if not results:
        return ToolResult(ok=True, output="(no files matched)", meta={"count": 0})
    return ToolResult(ok=True, output="\n".join(sorted(results)), meta={"count": len(results)})


def project_overview(path: str = "."):
    """A fast orientation pass: languages, entry points, manifests, layout.

    Saves the agent from opening a dozen files just to work out what kind of project
    it's in - which on a slow local model is a meaningful chunk of the whole task.
    """
    base = Path(path).expanduser().resolve()
    if not base.is_dir():
        return ToolResult(ok=False, error=f"{base} is not a directory")

    ext_counts = Counter()
    total_files = 0
    top_dirs = []

    try:
        for entry in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            if entry.name in IGNORE_DIRS or entry.name.startswith("."):
                continue
            if entry.is_dir():
                top_dirs.append(entry.name + "/")
    except OSError as e:
        return ToolResult(ok=False, error=f"Could not read {base}: {e}")

    for f in base.rglob("*"):
        if f.is_dir() or any(part in IGNORE_DIRS for part in f.parts):
            continue
        total_files += 1
        if f.suffix in _CODE_EXTS:
            ext_counts[f.suffix] += 1
        if total_files > 20000:
            break

    manifests = [m for m in _MANIFESTS if (base / m).exists()]
    langs = ", ".join(f"{ext} ({n})" for ext, n in ext_counts.most_common(8)) or "none detected"

    lines = [
        f"Project: {base.name}  ({base})",
        f"Files scanned: {total_files:,}",
        f"Languages: {langs}",
        f"Manifests: {', '.join(manifests) if manifests else 'none found'}",
        f"Top-level dirs: {', '.join(top_dirs[:25]) if top_dirs else '(none)'}",
    ]

    readme = next((base / n for n in ("README.md", "readme.md", "README.rst") if (base / n).exists()), None)
    if readme:
        try:
            head = readme.read_text(encoding="utf-8", errors="replace")[:1200].strip()
            lines.append(f"\n--- {readme.name} (first 1200 chars) ---\n{head}")
        except OSError:
            pass

    return ToolResult(ok=True, output="\n".join(lines), meta={"files": total_files})
