"""Guardrails: where files may be written, and which shell commands deserve a hard look.

None of this is a sandbox - a local agent running local shell commands fundamentally
has the user's own privileges. The goal is narrower and still worth having: make the
*accidental* catastrophe hard (a model confidently rewriting ~/.ssh/config or running
`rm -rf ~` because it misread a path), and make the genuinely dangerous stuff visible in
the approval prompt instead of scrolling by as one more `run_command`.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import platform_compat as pc

# Paths that are never writable by a tool call, no matter what the workspace is set to.
# Reading is still allowed - the agent may legitimately need to look at a config file -
# but writing to any of these is refused outright rather than merely prompted for.
#
# The home-directory entries work identically cross-platform (Path.home() resolves to
# C:\Users\<name> on Windows just as well as /home/<name> on Linux). The OS-root entries
# don't: /etc, /usr, /bin etc. are meaningless path *components* on Windows - Path("/etc")
# there resolves to a drive-relative "C:\etc", protecting nothing real while creating a
# false sense of coverage - so Windows gets its own list of what actually matters there.
_HOME_PROTECTED = [
    Path.home() / ".ssh",
    Path.home() / ".aws",
    Path.home() / ".gnupg",
    Path.home() / ".kube",
    Path.home() / ".docker" / "config.json",
    Path.home() / ".config" / "gh",
    Path.home() / ".netrc",
    Path.home() / ".npmrc",
    Path.home() / ".pypirc",
    Path.home() / ".bash_history",
    Path.home() / ".zsh_history",
]

if pc.IS_WINDOWS:
    def _env_path(var: str, default: str) -> Path:
        return Path(os.environ.get(var, default))

    PROTECTED_WRITE_PATHS = _HOME_PROTECTED + [
        _env_path("WINDIR", r"C:\Windows"),
        _env_path("PROGRAMFILES", r"C:\Program Files"),
        _env_path("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        _env_path("PROGRAMDATA", r"C:\ProgramData"),
        _env_path("APPDATA", str(Path.home() / "AppData" / "Roaming")),
        _env_path("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")),
    ]
else:
    PROTECTED_WRITE_PATHS = _HOME_PROTECTED + [
        Path("/etc"),
        Path("/usr"),
        Path("/bin"),
        Path("/sbin"),
        Path("/System"),
        Path("/Library/LaunchDaemons"),
    ]

# Filenames that usually hold secrets. Writing to them is allowed (a .env is a normal
# thing to edit) but always requires explicit approval even in auto-accept mode.
#
# The (^|[\\/]) anchor matches a path *component* boundary on either separator - not just
# "/". Anchoring on "/" alone was a real, silent gap on Windows: str(path) there is
# "C:\proj\.env", the anchor never matched, and .env/id_rsa/credentials.json/secrets.yaml
# all sailed through auto-accept with no approval prompt at all.
SECRET_FILE_PATTERNS = [
    re.compile(r"(^|[\\/])\.env(\.|$)"),
    re.compile(r"(^|[\\/])(id_rsa|id_ed25519|id_ecdsa)(\.pub)?$"),
    re.compile(r"(^|[\\/])credentials(\.json|\.yaml|\.yml)?$"),
    re.compile(r"(^|[\\/])secrets?(\.json|\.yaml|\.yml|\.toml)$"),
    re.compile(r"\.pem$"),
    re.compile(r"\.p12$"),
    re.compile(r"\.keystore$"),
]


class PathRefused(Exception):
    """Raised when a path is outright refused (not merely in need of approval)."""


@dataclass
class CommandRisk:
    level: str  # "low" | "medium" | "high" | "critical"
    reasons: list

    @property
    def needs_approval(self) -> bool:
        return self.level != "low"

    @property
    def bypasses_auto_accept(self) -> bool:
        """Critical commands are confirmed even with auto-accept on. Auto-accept is
        meant to save you from clicking through fifty `read_file`s, not to hand over
        an unattended `rm -rf`."""
        return self.level == "critical"


# (pattern, level, human explanation). Ordered roughly worst-first for nicer messages.
_COMMAND_RULES = [
    # A recursive force-delete aimed at a root-ish target is unrecoverable; the same
    # command aimed at ./build is a Tuesday. Keep the distinction, or the prompt cries
    # wolf often enough that people stop reading it.
    (re.compile(r"\brm\s+(-\S+\s+)*(/|~|\$HOME|/\*|~/\*)\s*($|\s)"), "critical",
     "recursive delete targeting a root/home path"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*f|"
                r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*f[a-zA-Z]*[rR]"), "high",
     "recursive force-delete (rm -rf)"),
    (re.compile(r"\bmkfs\b|\bfdisk\b|\bdiskutil\s+erase"), "critical", "formats a disk"),
    (re.compile(r"\bdd\s+.*of=/dev/"), "critical", "raw write to a device"),
    (re.compile(r":\(\)\s*\{.*\|.*&.*\}\s*;?\s*:"), "critical", "fork bomb"),
    (re.compile(r">\s*/dev/[sh]d[a-z]"), "critical", "overwrites a raw disk device"),
    (re.compile(r"\bcurl\b[^|]*\|\s*(sudo\s+)?(ba|z|k)?sh|"
                r"\bwget\b[^|]*\|\s*(sudo\s+)?(ba|z|k)?sh"), "critical",
     "pipes a downloaded script straight into a shell"),
    (re.compile(r"\bchmod\s+(-R\s+)?777\s+/(\s|$)"), "critical", "world-writable root"),
    (re.compile(r"\bgit\s+push\b.*(--force\b|-f\b)"), "high", "force-push rewrites remote history"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "high", "discards uncommitted work"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fd]"), "high", "deletes untracked files"),
    (re.compile(r"\bgit\s+checkout\s+\.\s*$|\bgit\s+restore\s+\.\s*$"), "high",
     "discards all local changes"),
    (re.compile(r"\bsudo\b|\bdoas\b"), "high", "runs as root"),
    (re.compile(r"\bnpm\s+publish\b|\byarn\s+publish\b|\bpnpm\s+publish\b|"
                r"\btwine\s+upload\b|\bcargo\s+publish\b"), "high",
     "publishes a package publicly"),
    (re.compile(r"\bgh\s+(repo\s+delete|release\s+create)\b"), "high", "changes a public GitHub resource"),
    (re.compile(r"\bkubectl\s+(delete|apply)\b|\bterraform\s+(apply|destroy)\b"), "high",
     "mutates real infrastructure"),
    (re.compile(r"\bdocker\s+(system\s+prune|volume\s+rm)\b"), "high", "deletes docker data"),
    (re.compile(r"\bshutdown\b|\breboot\b|\bhalt\b"), "high", "powers off the machine"),
    (re.compile(r"\bkillall\b|\bpkill\b"), "medium", "kills processes by name"),
    (re.compile(r"\brm\b"), "medium", "deletes files"),
    (re.compile(r"\bmv\b|\bmove\b"), "medium", "moves/renames files"),
    (re.compile(r"\bgit\s+(commit|merge|rebase|cherry-pick|revert)\b"), "medium",
     "changes git history"),
    (re.compile(r"\bgit\s+push\b"), "medium", "pushes to a remote"),
    (re.compile(r"\b(pip|pip3|npm|yarn|pnpm|brew|apt|apt-get|cargo|gem)\s+(install|add|remove|uninstall)\b"),
     "medium", "installs or removes packages"),
    (re.compile(r"\b(curl|wget)\b"), "medium", "makes a network request"),
    (re.compile(r">\s*/|>>\s*/"), "medium", "writes to an absolute path"),

    # --- Windows / PowerShell / cmd.exe equivalents of the above. Unconditional (not
    # gated on IS_WINDOWS): these strings essentially never appear in a legitimate POSIX
    # command, so matching them is harmless there, and it means run_command still gets
    # classified correctly if the user has pwsh/cmd available on a POSIX box, or if this
    # ever runs through WSL/git-bash where either dialect might show up.
    # Two independent lookaheads rather than one linear pattern, since the verb, the
    # recursive flag, and the target can appear in any order ("Remove-Item -Recurse
    # -Force $x" vs "Remove-Item -Force -Recurse $x" are both real usage).
    (re.compile(
        r"(?=.*\b(del|erase|rd|rmdir)\b.*?/s\b|.*Remove-Item\b.*-Recurse\b|.*\bri\b.*-[rR]\b)"
        r"(?=.*([a-zA-Z]:\\?\*?\s*$|%USERPROFILE%|\$env:USERPROFILE|~\\))",
        re.IGNORECASE,
    ), "critical", "recursive delete targeting a root/home-shaped path"),
    (re.compile(r"\b(del|erase)\b.*?/s\b|\brd\s+/s\b|\brmdir\s+/s\b|"
                r"Remove-Item\b.*-Recurse\b|\bri\b.*-[rR]\b", re.IGNORECASE),
     "high", "recursive delete"),
    (re.compile(r"\bformat\s+[a-zA-Z]:|\bdiskpart\b|Clear-Disk\b|Initialize-Disk\b"),
     "critical", "formats or repartitions a disk"),
    (re.compile(r"(Invoke-WebRequest|iwr|Invoke-RestMethod|irm)\b[^|]*\|\s*(Invoke-Expression|iex)\b|"
                r"certutil\s+.*-urlcache"), "critical",
     "pipes a downloaded script straight into a shell"),
    (re.compile(r"\bicacls\b.*\b(Everyone|/grant)\b|\btakeown\b.*/r\b", re.IGNORECASE), "critical",
     "grants broad filesystem permissions"),
    (re.compile(r"\brunas\b|Start-Process\b.*-Verb\s+RunAs|\bgsudo\b"), "high", "runs elevated"),
    (re.compile(r"Stop-Computer\b|Restart-Computer\b"), "high", "powers off the machine"),
    (re.compile(r"taskkill\s+.*/F\b|Stop-Process\b.*-Force"), "medium", "kills processes"),
    (re.compile(r"\b(winget|choco|scoop)\s+(install|uninstall|remove)\b"), "medium",
     "installs or removes packages"),
    (re.compile(r"vssadmin\s+delete\s+shadows|\bwbadmin\s+delete\b"), "critical",
     "deletes Windows shadow copies/backups (a ransomware-shaped action)"),
    (re.compile(r"\breg\s+delete\b"), "high", "deletes a registry key"),
    (re.compile(r"\bbcdedit\b"), "high", "changes boot configuration"),
    (re.compile(r"\bcipher\s+/w\b"), "medium", "securely wipes free disk space"),
    (re.compile(r"Set-ExecutionPolicy\b.*\bBypass\b|Set-ExecutionPolicy\b.*\bUnrestricted\b"),
     "medium", "disables PowerShell's script-execution safeguard"),
]


def assess_command(command: str) -> CommandRisk:
    """Classify a shell command. Conservative by design: unknown commands are 'low',
    since the permission system already prompts for every run_command by default -
    this only decides how loudly to shout and whether auto-accept applies."""
    reasons = []
    worst = "low"
    order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    for pattern, level, why in _COMMAND_RULES:
        if pattern.search(command):
            reasons.append(why)
            if order[level] > order[worst]:
                worst = level
    return CommandRisk(level=worst, reasons=reasons)


def is_secret_path(path: Path) -> bool:
    s = str(path)
    return any(p.search(s) for p in SECRET_FILE_PATTERNS)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


@dataclass
class WorkspaceGuard:
    """Decides whether a tool may write to a given path.

    `root` is the directory geo was started in. Writes inside it are normal. Writes
    outside it still work, but are treated as a deliberate act: they need approval
    every time and say so loudly, because "the model wandered out of the project and
    started editing dotfiles" is the failure mode worth catching.
    """

    root: Path
    allow_outside: bool = False

    def check_write(self, path: str) -> tuple:
        """Returns (allowed, requires_explicit_approval, reason).

        Raises PathRefused for paths that are never writable.
        """
        p = Path(path).expanduser()
        try:
            p = p.resolve()
        except OSError as e:
            raise PathRefused(f"cannot resolve path: {e}")

        for protected in PROTECTED_WRITE_PATHS:
            if p == protected or _is_within(p, protected):
                raise PathRefused(
                    f"{p} is inside a protected location ({protected}) that geocentric will not write to"
                )

        # Writing into .git internals corrupts repos in confusing ways; the git tools
        # exist for a reason. (.gitignore / .github and friends are unaffected - their
        # path components are ".gitignore"/".github", not ".git".) Case-insensitive
        # compare: NTFS is case-preserving but not case-sensitive, so a literal ".GIT"
        # is the same directory there and would otherwise slip past a bare "in" check.
        if any(part.lower() == ".git" for part in p.parts):
            raise PathRefused(f"{p} is inside a .git directory; use the git tools instead")

        if is_secret_path(p):
            return True, True, f"{p.name} looks like it holds credentials"

        if not _is_within(p, self.root):
            if not self.allow_outside:
                return True, True, f"{p} is outside the workspace ({self.root})"
            return True, False, ""

        return True, False, ""

    def describe(self) -> str:
        return f"{self.root}" + ("  (outside-workspace writes allowed)" if self.allow_outside else "")
