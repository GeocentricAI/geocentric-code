"""Global + per-project configuration for geocentric."""
from __future__ import annotations

import json
import os
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

GLOBAL_DIR = Path.home() / ".geocentric"
GLOBAL_CONFIG_PATH = GLOBAL_DIR / "config.json"

PROJECT_DIRNAME = ".geocentric"
PROJECT_CONFIG_NAME = "config.json"
COMMANDS_DIRNAME = "commands"

DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# The "surprise me" default-model pool: something in the 9-14B range, rolled fresh each
# launch - small enough to be responsive, big enough to be useful.
PREFERRED_PARAM_RANGE = (9.0, 14.0)

# Ollama exposes no generic reasoning-token budget the way hosted APIs do. The real
# levers are: whether `think` is requested, how many tokens the model may spend, and how
# hard the prompt pushes it to deliberate. gpt-oss models are the exception - Ollama
# passes graduated low/medium/high reasoning effort through natively for those.
EFFORT_LEVELS = ["low", "medium", "high", "xhigh", "max", "ultracode"]

EFFORT_PROFILES = {
    "low": {"think": False, "num_predict": 1024, "nudge": ""},
    "medium": {"think": True, "num_predict": 2048, "nudge": ""},
    "high": {"think": True, "num_predict": 4096, "nudge": "Think carefully before answering."},
    "xhigh": {
        "think": True, "num_predict": 8192,
        "nudge": "Think extensively: consider multiple approaches and edge cases before answering.",
    },
    "max": {
        "think": True, "num_predict": 16384,
        "nudge": (
            "Think as thoroughly as possible: explore alternatives and verify your reasoning "
            "with tools (re-read files, re-run things) before finalizing."
        ),
    },
    "ultracode": {
        "think": True, "num_predict": 32768,
        "nudge": (
            "Maximum effort. Reason exhaustively step by step, verify every claim with tools "
            "rather than assumption, check edge cases, and do not stop until you are certain "
            "the solution is correct and complete."
        ),
    },
}

_GPT_OSS_THINK_LEVEL = {
    "low": "low", "medium": "medium", "high": "high",
    "xhigh": "high", "max": "high", "ultracode": "high",
}


def think_value_for_model(effort: str, model_name: str):
    """What to put in the `think` field of an /api/chat request for this effort+model."""
    if "gpt-oss" in model_name.lower():
        return _GPT_OSS_THINK_LEVEL.get(effort, "medium")
    return EFFORT_PROFILES.get(effort, EFFORT_PROFILES["medium"])["think"]


@dataclass
class Config:
    model: Optional[str] = None
    ollama_host: str = DEFAULT_OLLAMA_HOST
    ollama_api_key: str = ""                 # only needed for a remotely-hosted Ollama behind auth
    yolo: bool = False                       # auto-approve tool calls
    always_allow: list = field(default_factory=list)
    theme: str = "geocentric"
    effort: str = "medium"
    onboarded: bool = False
    context_tokens: int = 0                  # num_ctx to request; 0 = auto (see context.resolve_window)
    allow_outside_workspace: bool = False    # let tools write outside the project dir
    auto_compact: bool = True
    show_diffs: bool = True
    max_diff_lines: int = 80
    autosave_sessions: bool = True

    @classmethod
    def load(cls, project_root: Optional[Path] = None) -> "Config":
        """Global config, then per-project overrides layered on top.

        Per-project wins so a repo can pin a model or loosen a setting without the user
        having to remember to flip it back when they switch projects.
        """
        data = dict(asdict(cls()))
        for path in [GLOBAL_CONFIG_PATH] + (
            [project_root / PROJECT_DIRNAME / PROJECT_CONFIG_NAME] if project_root else []
        ):
            if not path.exists():
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                continue
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if k in data})
        try:
            return cls(**data)
        except TypeError:
            return cls()

    def save(self) -> None:
        GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
        GLOBAL_CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def project_dir(root: Path) -> Path:
    p = root / PROJECT_DIRNAME
    is_new = not p.exists()
    p.mkdir(parents=True, exist_ok=True)
    if is_new:
        # Keep geocentric's own state out of the user's `git status`.
        (p / ".gitignore").write_text("*\n", encoding="utf-8")
    return p


def sessions_dir(root: Path) -> Path:
    p = project_dir(root) / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def commands_dir(root: Path) -> Path:
    return project_dir(root) / COMMANDS_DIRNAME


def journal_path(root: Path) -> Path:
    return project_dir(root) / "edit_journal.jsonl"


def _guess_param_size_b(model_name: str, size_bytes: int) -> float:
    """Best-effort parameter count in billions, from the model tag or its size on disk."""
    name = (model_name or "").lower()
    for token in name.replace(":", "-").split("-"):
        token = token.strip()
        if token.endswith("b") and token[:-1].replace(".", "", 1).isdigit():
            try:
                return float(token[:-1])
            except ValueError:
                pass
    # Fallback: roughly 0.6GB per billion params at Q4-ish quantization.
    return round((size_bytes / (1024 ** 3)) / 0.6, 1) if size_bytes else 0.0


def pick_random_default_model(models: list) -> Optional[str]:
    """Pick a random model in PREFERRED_PARAM_RANGE, preferring coding-tuned ones."""
    if not models:
        return None
    lo, hi = PREFERRED_PARAM_RANGE
    in_range = []
    for m in models:
        name = m.get("name") or m.get("model")
        b = _guess_param_size_b(name, m.get("size", 0))
        if lo <= b <= hi:
            in_range.append(name)
    coders = [n for n in in_range if any(k in n.lower() for k in ("coder", "code", "dev"))]
    pool = coders or in_range or [m.get("name") or m.get("model") for m in models]
    return random.choice(pool) if pool else None
