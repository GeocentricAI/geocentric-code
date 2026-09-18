"""Everything about what the model actually sees: project briefings, @file mentions,
how full the context window is, and when to compact.

Local models tend to have much smaller context windows than hosted ones (8k-32k is
typical where a hosted model might have 200k), so budgeting is not a nicety here - it's
the difference between a session that works and one that starts silently forgetting the
beginning of the task. Everything in this module exists to keep that visible and managed.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Files a project may use to brief a coding agent. Read in order; all that exist are
# included. The non-geocentric names are deliberate: if someone already wrote a briefing
# for another agent, there's no reason to make them write it again.
PROJECT_CONTEXT_FILENAMES = [
    "GEOCENTRIC.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".github/copilot-instructions.md",
]

MAX_CONTEXT_FILE_BYTES = 32_000
MAX_MENTION_BYTES = 100_000
MAX_PARENT_WALK = 6  # how far up to look for a monorepo-level briefing

# Fallback when Ollama doesn't report a context length. Conservative on purpose:
# overestimating the window means silent truncation by the server, which is far more
# confusing to debug than compacting a bit too eagerly.
DEFAULT_CONTEXT_TOKENS = 8192

# Ollama does NOT use a model's full advertised context by default - unless the model's
# Modelfile sets num_ctx (most don't) it falls back to its own default of 4096, no matter
# that the model card says 131072. So we always pass num_ctx explicitly: otherwise the
# budget meter divides by a window we aren't actually getting, reads reassuringly low,
# and the server quietly truncates the front of the conversation instead.
#
# The cap exists because KV-cache memory scales linearly with num_ctx, and this is
# someone's own GPU - a 128k window would reserve gigabytes for a window an agentic
# coding session almost never fills. 16k is a good balance; /context shows the real
# number and `context_tokens` in config overrides it.
OLLAMA_DEFAULT_NUM_CTX = 4096
AUTO_CONTEXT_CAP = 16384


def resolve_window(model_max: int, configured: int = 0) -> int:
    """The context window we will actually request via num_ctx."""
    if configured and configured > 0:
        return min(configured, model_max) if model_max else configured
    if not model_max:
        return DEFAULT_CONTEXT_TOKENS
    return min(model_max, AUTO_CONTEXT_CAP)

# Compact when we cross this fraction of the window. Leaves room for the reply plus a
# couple of tool round-trips, which is where overflow usually actually bites.
COMPACT_THRESHOLD = 0.75

_MENTION_RE = re.compile(r"(?:^|\s)@([^\s@]+)")


def estimate_tokens(text: str) -> int:
    """Rough token count. ~3.7 chars/token is a decent middle ground across the
    tokenizers these models use; we deliberately round up rather than down so the
    budget errs toward compacting early instead of overflowing."""
    if not text:
        return 0
    return int(len(text) / 3.7) + 1


def estimate_messages_tokens(messages: list) -> int:
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content)
        total += estimate_tokens(content) + 4  # per-message role/framing overhead
        for call in m.get("tool_calls") or []:
            total += estimate_tokens(json.dumps(call))
    return total


def context_length_for(show_response: dict) -> int:
    """Pull the context window out of an Ollama /api/show payload.

    The key is namespaced by architecture (llama.context_length, qwen3moe.context_length,
    gemma3.context_length, ...) so we look for any key that ends the right way rather
    than maintaining a list of architectures that will inevitably go stale.
    """
    info = (show_response or {}).get("model_info") or {}
    for key, value in info.items():
        if key.endswith(".context_length") and isinstance(value, int) and value > 0:
            return value
    return DEFAULT_CONTEXT_TOKENS


@dataclass
class ProjectContext:
    """The briefing assembled from a project's own context files."""

    sources: list = field(default_factory=list)  # (path, text)

    @property
    def text(self) -> str:
        if not self.sources:
            return ""
        blocks = []
        for path, body in self.sources:
            blocks.append(f"--- {path} ---\n{body.strip()}")
        return "\n\n".join(blocks)

    @property
    def is_empty(self) -> bool:
        return not self.sources

    def describe(self) -> str:
        if not self.sources:
            return "(none)"
        return ", ".join(p for p, _ in self.sources)


def load_project_context(root: Path) -> ProjectContext:
    """Read whichever agent-briefing files this project has.

    Also walks up toward the filesystem root so a briefing at the top of a monorepo
    still applies when geo is started in a subpackage. Nearer files come last so their
    guidance reads as the more specific, overriding voice.
    """
    ctx = ProjectContext()
    seen = set()

    # Walk up a bounded number of levels so a briefing at the top of a monorepo still
    # applies in a subpackage, without wandering to / and picking up something unrelated.
    # The root itself is always included, even when the project lives outside $HOME.
    home = Path.home()
    chain = [root]
    current = root
    for _ in range(MAX_PARENT_WALK):
        if current.parent == current or current == home:
            break
        current = current.parent
        chain.append(current)

    for directory in reversed(chain):
        for name in PROJECT_CONTEXT_FILENAMES:
            p = directory / name
            if not p.is_file() or p in seen:
                continue
            try:
                body = p.read_text(encoding="utf-8", errors="replace")[:MAX_CONTEXT_FILE_BYTES]
            except OSError:
                continue
            if body.strip():
                seen.add(p)
                try:
                    label = str(p.relative_to(root))
                except ValueError:
                    label = str(p)
                ctx.sources.append((label, body))
    return ctx


@dataclass
class Mention:
    raw: str
    path: Path
    ok: bool
    body: str = ""
    error: str = ""


def expand_mentions(text: str, root: Path) -> tuple:
    """Find @path references in a user message and read those files.

    Returns (cleaned_text, mentions). The @token is left in the visible text - it reads
    naturally as part of the sentence - and the file bodies get appended as context so
    the model has the actual content rather than a filename it has to go fetch.
    """
    mentions = []
    for match in _MENTION_RE.finditer(text):
        raw = match.group(1).rstrip(".,;:!?)")
        # A leading "/" or "~" only covers POSIX absolute paths; a Windows path like
        # "C:\project\file.py" or "C:/project/file.py" starts with neither. Path.is_absolute()
        # understands drive letters natively, so ask it instead of guessing from the string.
        fragment = Path(raw).expanduser()
        candidate = fragment if fragment.is_absolute() else (root / raw).expanduser()
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if candidate.is_dir():
            try:
                listing = "\n".join(sorted(p.name + ("/" if p.is_dir() else "") for p in candidate.iterdir())[:200])
            except OSError as e:
                mentions.append(Mention(raw=raw, path=candidate, ok=False, error=str(e)))
                continue
            mentions.append(Mention(raw=raw, path=candidate, ok=True, body=listing))
        elif candidate.is_file():
            try:
                body = candidate.read_text(encoding="utf-8", errors="replace")[:MAX_MENTION_BYTES]
            except OSError as e:
                mentions.append(Mention(raw=raw, path=candidate, ok=False, error=str(e)))
                continue
            mentions.append(Mention(raw=raw, path=candidate, ok=True, body=body))
        # A bare @word that isn't a path is just prose ("@ me later") - ignore silently.
    return text, mentions


def build_mention_block(mentions: list, root: Path) -> str:
    usable = [m for m in mentions if m.ok]
    if not usable:
        return ""
    parts = ["The user referenced these files; their current contents are below."]
    for m in usable:
        try:
            label = m.path.relative_to(root)
        except ValueError:
            label = m.path
        kind = "directory listing" if m.path.is_dir() else "file"
        parts.append(f"\n--- {label} ({kind}) ---\n{m.body}")
    return "\n".join(parts)


@dataclass
class ContextBudget:
    """Tracks how full the window is, so the UI can show it and the agent can act."""

    window: int = DEFAULT_CONTEXT_TOKENS
    used: int = 0

    @property
    def fraction(self) -> float:
        if self.window <= 0:
            return 0.0
        return min(self.used / self.window, 1.0)

    @property
    def percent(self) -> int:
        return int(self.fraction * 100)

    @property
    def should_compact(self) -> bool:
        return self.fraction >= COMPACT_THRESHOLD

    @property
    def remaining(self) -> int:
        return max(self.window - self.used, 0)

    def bar(self, width: int = 10) -> str:
        filled = int(self.fraction * width)
        # Show a sliver as soon as anything is used, so "in use" never looks like "empty".
        if filled == 0 and self.used > 0:
            filled = 1
        return "█" * filled + "░" * (width - filled)

    @staticmethod
    def _compact(n: int) -> str:
        if n >= 1000:
            return f"{n / 1000:.1f}k".replace(".0k", "k")
        return str(n)

    def label(self) -> str:
        """e.g. '1.2k/16k' - always informative, unlike a percentage that rounds to 0."""
        return f"{self._compact(self.used)}/{self._compact(self.window)}"


class FileRegistry:
    """Remembers the mtime of every file the agent has read this session.

    This exists to catch a specific, genuinely nasty failure: the agent reads a file,
    you edit it in your editor, then the agent applies an edit based on what it read
    minutes ago and silently clobbers your change. On an edit we compare mtimes and
    refuse if the file moved under us.
    """

    def __init__(self):
        self._seen: dict = {}

    def record(self, path: Path) -> None:
        try:
            self._seen[str(path)] = path.stat().st_mtime
        except OSError:
            pass

    def has_read(self, path: Path) -> bool:
        return str(path) in self._seen

    def changed_since_read(self, path: Path) -> bool:
        key = str(path)
        if key not in self._seen:
            return False
        try:
            return path.stat().st_mtime > self._seen[key] + 1e-6
        except OSError:
            return False

    def forget(self, path: Path) -> None:
        self._seen.pop(str(path), None)

    def count(self) -> int:
        return len(self._seen)
