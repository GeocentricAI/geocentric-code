"""JSON bridge between the Geocentric engine and a native GUI shell.

Speaks newline-delimited JSON: one command object per line on stdin, one event object
per line on stdout. This module intentionally contains no agent logic of its own — it
just wires up the same Agent / Runner / Session / commands machinery the CLI uses
(see cli.py) and re-routes their output as structured events instead of drawing to a
terminal. Rich's Console still gets used underneath (commands.py and ui/render.py print
to it), but with record=True and a devnull sink so nothing hits a real terminal; the
recorded text is drained after each command and forwarded as a generic event for
anything that doesn't already have a structured equivalent (e.g. /tools, /jobs tables).

Run as: python3 -m geocentric.gui_bridge --cwd /path/to/project [--model NAME] [--yolo]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from . import cluster as cluster_mod
from . import commands
from . import session as session_mod
from . import tools as tools_mod
from .agent import Agent
from .cli import ContextController
from .config import Config, pick_random_default_model
from .ollama_client import OllamaClient, OllamaConnectionError
from .permissions import Decision, PermissionManager
from .planning import REVISE_PROMPT, parse_plan
from .runner import Runner
from .safety import WorkspaceGuard
from .tools.interact import set_ask_handler
from .tools.peer import set_delegate_handler
from .tools.settings import set_context_controller

# The local half of exo's Ollama-compatible endpoint (see cluster_mode docs at
# github.com/exo-explore/exo) - only ever used while cluster mode is active,
# and only after a ping confirms something is actually listening there.
EXO_HOST = "http://localhost:52415/ollama"

_DECISIONS = {"once": Decision.ALLOW_ONCE, "always": Decision.ALLOW_ALWAYS, "deny": Decision.DENY}

_stdout_lock = threading.Lock()


def emit(event: dict) -> None:
    try:
        line = json.dumps(event, default=str)
    except (TypeError, ValueError):
        line = json.dumps({"type": "error", "message": "failed to serialize an event"})
    with _stdout_lock:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _sink_with_plan_parsing(event: dict) -> None:
    """Augments plan_proposal events with the same structured fields the CLI's plan
    panel renders from (goal/files/steps/risks/verification), so the GUI doesn't have
    to re-implement plan-text parsing."""
    if event.get("type") == "plan_proposal":
        plan = parse_plan(event.get("text", ""))
        event = dict(event, goal=plan.goal, files=plan.files, steps=plan.steps,
                     risks=plan.risks, verification=plan.verification, structured=plan.is_structured)
    emit(event)


def drain_console(console: Console, event_type: str = "command_output") -> None:
    text = console.export_text(clear=True).strip("\n")
    if text:
        emit({"type": event_type, "text": text})


def _emit_history(agent) -> None:
    """Replays a resumed session's user/assistant turns as timeline entries,
    so the GUI shows the actual conversation instead of just the "resumed
    <id> - N turns" status line drained from the console.

    Tool calls and raw reasoning aren't replayed - they're transient, mid-turn
    detail that doesn't survive a resume in the CLI transcript either, and
    reconstructing them from the stored messages would be guesswork (results
    were truncated for context, not preserved verbatim).
    """
    entries = []
    for m in agent.messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role == "user":
            entries.append({"role": "user", "text": content})
        elif role == "assistant" and content:
            entries.append({"role": "assistant", "text": content})
    if entries:
        emit({"type": "history", "entries": entries})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geocentric-gui-bridge")
    p.add_argument("--cwd", default=".")
    p.add_argument("--model")
    p.add_argument("--host")
    p.add_argument("--yolo", action="store_true")
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.is_dir():
        emit({"type": "fatal", "message": f"no such directory: {cwd}"})
        return
    os.chdir(cwd)

    config = Config.load(project_root=cwd)
    if args.host:
        config.ollama_host = args.host
    if args.yolo:
        config.yolo = True

    devnull = open(os.devnull, "w")
    console = Console(record=True, force_terminal=False, no_color=True, width=100, file=devnull)

    client = OllamaClient(host=config.ollama_host, api_key=config.ollama_api_key or None)
    reachable = client.ping()
    if not reachable:
        emit({"type": "ollama_unreachable", "host": config.ollama_host})

    model = args.model or config.model
    if not model and reachable:
        try:
            models = client.list_models()
            model = pick_random_default_model(models)
        except (OllamaConnectionError, Exception):
            model = None
    model = model or "qwen2.5-coder:14b"  # placeholder; the first real call surfaces the true error

    runner_ref: dict = {}

    def prompt_fn(tool_name, call_args, danger, reasons=None):
        return runner_ref["runner"].request_approval(tool_name, call_args, danger, reasons or [])

    permissions = PermissionManager(config=config, prompt_fn=prompt_fn)
    guard = WorkspaceGuard(root=cwd, allow_outside=config.allow_outside_workspace)

    agent = Agent(client=client, model=model, permissions=permissions, console=console,
                  cwd=str(cwd), guard=guard, event_sink=_sink_with_plan_parsing)

    session = session_mod.Session(cwd)
    ctx = SimpleNamespace(
        console=console, agent=agent, config=config, permissions=permissions,
        client=client, model=model, cwd=cwd, runner=None, session=session,
        custom_commands=commands.load_custom_commands(cwd),
        new_session=lambda: session_mod.Session(cwd),
        mode_histories={},  # workspace mode -> that mode's own agent.messages
    )
    ctx.context_controller = ContextController(agent, config)
    set_context_controller(ctx.context_controller)

    def on_idle():
        if config.autosave_sessions:
            session.save(agent)

    runner = Runner(agent, console, on_idle=on_idle, event_sink=_sink_with_plan_parsing)
    ctx.runner = runner
    runner_ref["runner"] = runner
    set_ask_handler(lambda items: runner.ask_questions(items))

    ctx.cluster = cluster_mod.ClusterNode(
        on_event=emit, on_delegate_task=lambda task: _run_delegated_task(ctx, task),
    )
    ctx.cluster_original_host = config.ollama_host
    set_delegate_handler(lambda task: ctx.cluster.delegate(task))

    emit({
        "type": "ready", "cwd": str(cwd), "model": model, "effort": config.effort,
        "theme": config.theme, "yolo": config.yolo, "ollama_reachable": reachable,
        "ollama_host": config.ollama_host, "has_ollama_api_key": bool(config.ollama_api_key),
        "context_window": agent.context_window(), "tool_count": len(tools_mod.TOOLS),
    })

    _command_loop(ctx, console)

    ctx.cluster.stop_linking()
    from .tools.shell import JOBS
    JOBS.kill_all()
    if config.autosave_sessions and agent.turns:
        session.save(agent)


def _run_delegated_task(ctx, task: str) -> str:
    """Runs a task handed over by a paired peer, on this machine's own model.

    A fresh, isolated Agent rather than the shared `ctx.agent` - it must not touch the
    local user's own conversation, and it must not block waiting on approvals nobody's
    watching for. plan_mode keeps it read-only (investigate/analyze/draft only, no file
    writes) so there's no approval prompt to coordinate across two people's machines.
    """
    delegate_agent = Agent(
        client=ctx.client, model=ctx.agent.model, permissions=ctx.permissions, console=ctx.console,
        cwd=str(ctx.cwd), guard=WorkspaceGuard(root=ctx.cwd, allow_outside=ctx.config.allow_outside_workspace),
        workspace_mode="code",
    )
    delegate_agent.plan_mode = True
    delegate_agent.add_user_message(task)
    try:
        result = delegate_agent.run_turn(quiet=True)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    return result or "(the peer's agent produced no answer)"


def _set_cluster_mode(ctx, mode: str) -> None:
    """cluster mode hands inference to a local `exo` cluster; orchestration mode keeps
    each machine on its own model and lets them delegate tasks to each other instead.
    Only one can be active - switching (or clearing) always restores the Ollama host
    cluster mode may have swapped out first, so a failed or abandoned link never leaves
    the app pointed at a dead endpoint."""
    if ctx.client.host != ctx.cluster_original_host:
        ctx.client.host = ctx.cluster_original_host

    if mode == "cluster":
        if not shutil.which("exo"):
            emit({
                "type": "cluster_mode_error",
                "message": "exo isn't installed on this Mac. See https://github.com/exo-explore/exo for "
                            "install instructions, then try again.",
            })
            ctx.cluster.set_mode(None)
            return
        probe = OllamaClient(host=EXO_HOST)
        if not probe.ping():
            emit({
                "type": "cluster_mode_error",
                "message": "exo is installed but nothing answered at " + EXO_HOST + " - start it "
                            "(`exo`) on both linked Macs, then try again.",
            })
            ctx.cluster.set_mode(None)
            return
        ctx.client.host = EXO_HOST

    ctx.cluster.set_mode(mode or None)


def _switch_mode(ctx, new_mode: str) -> None:
    """Swap in the conversation history for `new_mode`, stashing the current
    one first.

    Chat and Code used to be two labels on one shared `agent.messages` list -
    a code-mode system prompt (full tool access, engineering register) sitting
    next to chat-mode pleasantries in the same context, and every mode switch
    silently carrying one conversation's baggage into the other. Each mode now
    gets its own history, keyed in `ctx.mode_histories`, so switching modes
    means switching *conversations*, not just a label.
    """
    agent = ctx.agent
    old_mode = agent.workspace_mode
    if not new_mode or new_mode == old_mode:
        return
    ctx.mode_histories[old_mode] = agent.messages
    agent.set_workspace_mode(new_mode)
    if new_mode in ctx.mode_histories:
        agent.messages = ctx.mode_histories[new_mode]
        agent._sync_system_prompt(agent._supports_tools(agent.model))
    else:
        agent.reset()  # first visit to this mode this session - start it fresh
    agent.refresh_budget()


def _handle_send_message(ctx, console: Console, text: str, turn_id: str = "", mode: str = "") -> None:
    agent, runner = ctx.agent, ctx.runner
    if mode:
        _switch_mode(ctx, mode)
    stripped = text.strip()
    if not stripped:
        return

    if runner.pending_question and not stripped.startswith("/"):
        stripped = "/answer " + stripped

    if stripped.split(maxsplit=1)[0].lower() == "/theme" and " " not in stripped:
        emit({"type": "error", "message": "usage: /theme <name>  (geocentric, solar, nebula, voyager, eclipse)"})
        return

    if stripped.startswith("/"):
        result = commands.handle(stripped, ctx)
        drain_console(console)
        if result.quit:
            emit({"type": "quit"})
            return
        if not result.submit:
            if turn_id:
                emit({"type": "turn_finished", "turn_id": turn_id})
            return
        stripped = result.submit

    mentions = agent.add_user_message(stripped)
    if mentions:
        emit({"type": "mentions", "paths": [str(m.path) for m in mentions if m.ok]})
    runner.submit(stripped, already_added=True, turn_id=turn_id)


def _command_loop(ctx, console: Console) -> None:
    agent, runner = ctx.agent, ctx.runner
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            emit({"type": "error", "message": f"bad command json: {line[:200]}"})
            continue

        kind = cmd.get("type")
        try:
            if kind == "send_message":
                _handle_send_message(
                    ctx, console, cmd.get("text", ""),
                    turn_id=str(cmd.get("turn_id", "")), mode=str(cmd.get("mode", "")),
                )

            elif kind == "interrupt":
                runner.interrupt()

            elif kind == "approve":
                decision = _DECISIONS.get(cmd.get("decision", "deny"), Decision.DENY)
                runner.answer_approval(decision)

            elif kind == "answer_question":
                runner.answer_question(cmd.get("answer"))

            elif kind == "set_model":
                name = cmd.get("name", "")
                if name:
                    agent.set_model(name)
                    ctx.model = name
                    ctx.config.model = name
                    ctx.config.save()
                    emit({"type": "model_changed", "name": name, "context_window": agent.context_window()})

            elif kind == "set_effort":
                level = cmd.get("level", "medium")
                ctx.config.effort = level
                ctx.config.save()
                emit({"type": "effort_changed", "level": level})

            elif kind == "set_ollama_api_key":
                key = str(cmd.get("key", ""))
                ctx.config.ollama_api_key = key
                ctx.config.save()
                ctx.client.set_api_key(key or None)
                emit({"type": "ollama_api_key_changed", "has_key": bool(key)})

            elif kind == "set_ollama_host":
                host = str(cmd.get("host", "")).strip()
                if host:
                    ctx.config.ollama_host = host
                    ctx.config.save()
                    ctx.client.host = host.rstrip("/")
                    ctx.cluster_original_host = host
                    reachable = ctx.client.ping()
                    emit({"type": "ollama_host_changed", "host": host, "ollama_reachable": reachable})

            elif kind == "set_yolo":
                ctx.config.yolo = bool(cmd.get("value"))
                emit({"type": "yolo_changed", "value": ctx.config.yolo})

            elif kind == "set_theme":
                name = cmd.get("name", "")
                if name:
                    ctx.config.theme = name
                    ctx.config.save()
                    emit({"type": "theme_changed", "name": name})

            elif kind == "set_mode":
                mode = str(cmd.get("mode", "code"))
                _switch_mode(ctx, mode)
                emit({"type": "mode_changed", "mode": agent.workspace_mode})

            elif kind == "list_models":
                try:
                    models = ctx.client.list_models()
                except Exception as e:
                    emit({"type": "error", "message": str(e)})
                else:
                    out = []
                    for m in models:
                        name = m.get("name") or m.get("model")
                        try:
                            caps = ctx.client.get_capabilities(name)
                        except Exception:
                            caps = []
                        out.append({
                            "name": name, "size": m.get("size", 0),
                            "tools": "tools" in caps, "thinking": "thinking" in caps,
                        })
                    emit({"type": "models", "models": out})

            elif kind == "list_sessions":
                metas = session_mod.list_sessions(ctx.cwd)
                emit({"type": "sessions", "sessions": [
                    {"id": m.id, "when": m.when, "age": m.age, "turns": m.turns,
                     "model": m.model, "title": m.title(80), "files_changed": m.files_changed}
                    for m in metas
                ]})

            elif kind == "new_session":
                agent.reset()
                ctx.session = ctx.new_session()
                emit({"type": "session_new", "id": ctx.session.id})

            elif kind == "resume_session":
                commands.handle(f"/resume {cmd.get('id', '')}".strip(), ctx)
                drain_console(console)
                _emit_history(agent)
                emit({"type": "session_resumed", "id": ctx.session.id})

            elif kind == "accept_plan":
                mode = cmd.get("mode", "manual")
                turn_id = str(cmd.get("turn_id", ""))
                agent.plan_mode = False
                agent.last_plan_text = ""
                if mode == "auto":
                    ctx.config.yolo = True
                runner.submit(
                    "Execute the plan you just described. Work through it step by step.",
                    already_added=False,
                    turn_id=turn_id,
                )

            elif kind == "revise_plan":
                agent.last_plan_text = ""
                feedback = cmd.get("feedback", "")
                runner.submit(
                    REVISE_PROMPT.format(feedback=feedback), already_added=False,
                    turn_id=str(cmd.get("turn_id", "")),
                )

            elif kind == "cancel_plan":
                agent.last_plan_text = ""
                emit({"type": "plan_cancelled"})

            elif kind == "list_tools":
                emit({"type": "tools", "tools": [
                    {"name": s.name, "description": s.description, "danger": s.danger,
                     "mutating": s.mutating, "concurrent_safe": s.concurrent_safe, "group": s.group}
                    for s in tools_mod.all_specs()
                ]})

            elif kind == "cluster_link_start":
                ctx.cluster.start_linking()

            elif kind == "cluster_link_stop":
                _set_cluster_mode(ctx, "")
                ctx.cluster.stop_linking()

            elif kind == "cluster_pair_request":
                ctx.cluster.request_pairing(str(cmd.get("id", "")))

            elif kind == "cluster_pair_answer":
                ctx.cluster.answer_pairing(str(cmd.get("id", "")), bool(cmd.get("accept")))

            elif kind == "cluster_set_mode":
                _set_cluster_mode(ctx, str(cmd.get("mode", "")))

            elif kind == "shutdown":
                break

            else:
                emit({"type": "error", "message": f"unknown command type: {kind!r}"})
        except Exception as e:
            emit({"type": "error", "message": f"bridge error handling {kind!r}: {type(e).__name__}: {e}"})


if __name__ == "__main__":
    main()
