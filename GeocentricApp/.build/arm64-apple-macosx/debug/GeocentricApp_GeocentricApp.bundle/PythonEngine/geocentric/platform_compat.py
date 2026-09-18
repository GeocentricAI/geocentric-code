"""Everything that differs between POSIX and Windows lives here, so the rest of the
codebase can stay platform-agnostic and just call into this module.

The core problem on Windows isn't that things fail loudly - it's that `shell=True`
quietly hands your command to cmd.exe, `os.killpg` doesn't exist, and file writes flip
to CRLF, all without an exception in sight. Everything here exists to make those
differences explicit instead of silent.
"""
from __future__ import annotations

import os
import shutil
import sys

IS_WINDOWS = os.name == "nt"

# The encoding/newline pair every text file read or written should use, on every
# platform. UTF-8 because Windows' locale-default codepage (cp1252 etc.) can't round-trip
# arbitrary source files or model output; newline="" because Path.read_text/write_text
# otherwise translate line endings on Windows, silently rewriting an LF file to CRLF the
# moment a single line in it is touched.
TEXT_ENCODING = "utf-8"
TEXT_NEWLINE = ""


def read_text_kwargs(errors: str = "strict") -> dict:
    return {"encoding": TEXT_ENCODING, "newline": TEXT_NEWLINE, "errors": errors}


def write_text_kwargs() -> dict:
    return {"encoding": TEXT_ENCODING, "newline": TEXT_NEWLINE}


# subprocess.run(..., text=True) with no encoding= falls back to the locale's preferred
# encoding - cp1252 on most Windows installs - while the console and most CLI tools
# actually emit UTF-8 or an OEM codepage. Pass this everywhere text output is captured.
SUBPROCESS_TEXT_KWARGS = {"encoding": "utf-8", "errors": "replace"}


def shell_executable():
    """The interpreter run_command should hand shell strings to.

    On POSIX this returns None - subprocess's own `shell=True` already does the right
    thing via /bin/sh. On Windows, `shell=True` invokes cmd.exe, which understands
    almost none of what a model trained mostly on bash will write (no $VAR, no `ls`,
    no `rm -rf`, no `&&`-as-bash-would-mean-it). PowerShell's Unix-alias set (ls, cat,
    cp, mv, rm, pwd, ps, kill, sort, tee, diff, sleep...) closes most of that gap, so we
    prefer it explicitly - pwsh (PowerShell 7+, if installed) over the bundled
    Windows PowerShell 5.1, since it's more actively maintained and more POSIX-flavored.
    """
    if not IS_WINDOWS:
        return None
    for exe in ("pwsh", "powershell"):
        path = shutil.which(exe)
        if path:
            return path
    return None  # fall back to bare shell=True (cmd.exe) if neither is on PATH


def build_shell_command(command: str):
    """What to actually pass to subprocess for a shell string, plus whether shell=True
    is needed. Returns (args_or_string, use_shell)."""
    exe = shell_executable()
    if exe is None:
        return command, True
    return [exe, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command], False


def popen_kwargs_for_job() -> dict:
    """Extra Popen kwargs so a background job's children die when the job is killed.

    POSIX: start_new_session makes the child a process-group leader, so os.killpg can
    take the whole tree down in one signal. Windows has no process groups in that sense;
    the equivalent is CREATE_NEW_PROCESS_GROUP, which lets us send CTRL_BREAK_EVENT or -
    more reliably, since not everything handles that signal - use `taskkill /T` to walk
    and kill the whole process tree by PID (see kill_process_tree below).
    """
    if IS_WINDOWS:
        # getattr with the documented literal (0x00000200) as fallback: this constant
        # only exists in the `subprocess` module's Windows build, so it can't be looked
        # up directly on a non-Windows interpreter - which matters for testing this
        # branch by simulation on a POSIX dev machine, not just for real Windows use.
        flag = getattr(subprocess_module(), "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        return {"creationflags": flag}
    return {"start_new_session": True}


def subprocess_module():
    import subprocess
    return subprocess


def kill_process_tree(pid: int) -> bool:
    """Kill a process and everything it spawned. Returns True if a kill was attempted
    (not necessarily that the process still existed - an already-dead PID isn't an error
    here, the goal state is 'not running' either way)."""
    subprocess = subprocess_module()
    if IS_WINDOWS:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, timeout=10,
            )
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError, OSError):
            return False


def force_kill_process_tree(pid: int) -> None:
    """Escalation after a graceful kill_process_tree didn't take within the timeout."""
    subprocess = subprocess_module()
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    else:
        import signal
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def devnull() -> str:
    return os.devnull  # "nul" on Windows, "/dev/null" on POSIX


def enable_windows_vt_mode() -> bool:
    """Turns on ANSI escape interpretation for the current console, best-effort.

    Rich detects VT support (via _windows.py) but never enables it - when it's off,
    Rich falls back to rendering through the legacy Win32 console API for its own
    console.print() calls, but anything writing raw ANSI directly (as the self-editing
    status line in ui/render.py does, since Rich's Live had its own cross-thread issues -
    see the project's own history on that) bypasses that fallback entirely and would
    print literal escape codes on an unpatched console. Modern Windows Terminal and
    PowerShell 7 already have this on; this specifically helps legacy conhost.exe.
    """
    if not IS_WINDOWS:
        return True
    try:
        import ctypes

        STD_OUTPUT_HANDLE = -11
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if not kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
            return False
        return True
    except Exception:
        return False


def reconfigure_stdio_utf8() -> None:
    """Windows' default console/pipe encoding is the locale codepage, which can't
    represent most of the box-drawing and emoji this UI uses once output is redirected
    (a pipe, `> file`, `| other-tool`) rather than attached to a real console. Safe to
    call unconditionally; a no-op-ish reconfigure on POSIX where stdio is UTF-8 already."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def shell_name() -> str:
    """What to call the shell in prompts/UI - informational only."""
    exe = shell_executable()
    if exe:
        return "PowerShell"
    if IS_WINDOWS:
        return "cmd.exe"
    return os.environ.get("SHELL", "/bin/sh").rsplit("/", 1)[-1]
