"""Approval flow for mutating tool calls (writes, shell commands, git commits, ...)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

from .config import Config


class Decision(Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"


@dataclass
class PermissionManager:
    config: Config
    prompt_fn: Optional[Callable] = None  # (tool, args, danger, reasons) -> Decision
    session_allow: set = field(default_factory=set)
    denied_count: int = 0
    approved_count: int = 0

    def is_pre_approved(self, tool_name: str) -> bool:
        return (
            self.config.yolo
            or tool_name in self.config.always_allow
            or tool_name in self.session_allow
        )

    def request(
        self,
        tool_name: str,
        args: dict,
        danger: str,
        reasons: Optional[list] = None,
        force_prompt: bool = False,
    ) -> bool:
        """Returns True if the call may proceed.

        `force_prompt` overrides auto-accept. It's used for the genuinely destructive
        cases (rm -rf /, writing outside the workspace, touching a credentials file):
        auto-accept exists to save you from clicking through fifty reads, not to hand
        over an unattended disk wipe.
        """
        if self.is_pre_approved(tool_name) and not force_prompt:
            self.approved_count += 1
            return True

        if self.prompt_fn is None:
            # No interactive surface (e.g. `geo -p` without --yolo): fail closed.
            self.denied_count += 1
            return False

        decision = self.prompt_fn(tool_name, args, danger, reasons or [])
        if decision == Decision.ALLOW_ONCE:
            self.approved_count += 1
            return True
        if decision == Decision.ALLOW_ALWAYS:
            # Deliberately not persisted to disk: "always" means this session. A
            # permanent grant should be a considered choice in the config file, not a
            # side effect of one hurried keypress.
            self.session_allow.add(tool_name)
            self.approved_count += 1
            return True
        self.denied_count += 1
        return False

    def set_yolo(self, value: bool) -> None:
        self.config.yolo = value

    def reset_session_grants(self) -> int:
        n = len(self.session_allow)
        self.session_allow.clear()
        return n
