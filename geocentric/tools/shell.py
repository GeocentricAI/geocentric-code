"""Shell + Python execution, including long-running background jobs."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field

from .. import platform_compat as pc
from .base import ToolResult, truncate_output


@dataclass
class Job:
    id: str
    command: str
    proc: subprocess.Popen
    started: float
    lines: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _reader: threading.Thread = None

    @property
    def running(self) -> bool:
        return self.proc.poll() is None

    @property
    def returncode(self):
        return self.proc.poll()

    def snapshot(self, tail: int = 80) -> str:
        with self.lock:
            return "".join(self.lines[-tail:])

    def append(self, text: str) -> None:
        with self.lock:
            self.lines.append(text)
            # Bound memory on chatty servers; we only ever show a tail anyway.
            if len(self.lines) > 4000:
                del self.lines[:2000]


class JobManager:
    """Tracks background processes started by the agent.

    A dev server or a ten-minute test suite shouldn't block the agent loop, and killing
    it should be one command rather than hunting for a PID. Jobs own their whole process
    tree so that killing one takes its children with it too - otherwise `npm run dev`
    leaves the actual node process alive and the port stays bound. On POSIX that's a
    process group (start_new_session + killpg); Windows has no equivalent concept, so
    kill_process_tree uses `taskkill /T` there instead - see platform_compat.
    """

    def __init__(self):
        self._jobs: dict = {}
        self._counter = 0
        self._lock = threading.Lock()

    def start(self, command: str, cwd: str = None) -> Job:
        with self._lock:
            self._counter += 1
            job_id = f"job{self._counter}"

        args, use_shell = pc.build_shell_command(command)
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            **pc.SUBPROCESS_TEXT_KWARGS,
            **pc.popen_kwargs_for_job(),
        )
        job = Job(id=job_id, command=command, proc=proc, started=time.time())

        def pump():
            try:
                for line in proc.stdout:
                    job.append(line)
            except Exception:
                pass

        job._reader = threading.Thread(target=pump, daemon=True)
        job._reader.start()
        self._jobs[job_id] = job
        return job

    def get(self, job_id: str):
        return self._jobs.get(job_id)

    def all(self) -> list:
        return list(self._jobs.values())

    def kill(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or not job.running:
            return False
        if not pc.kill_process_tree(job.proc.pid):
            try:
                job.proc.terminate()
            except Exception:
                return False
        try:
            job.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pc.force_kill_process_tree(job.proc.pid)
        return True

    def kill_all(self) -> int:
        n = 0
        for job in self.all():
            if job.running and self.kill(job.id):
                n += 1
        return n


JOBS = JobManager()


def _run(cmd, cwd=None, timeout=120, shell=False):
    # Popen + communicate(timeout=) instead of the subprocess.run() convenience wrapper,
    # specifically so we keep a handle to the process on timeout: run()'s own timeout
    # path only kills the direct child, orphaning anything *it* spawned (a shell running
    # a build tool that forks workers, say) - same process-tree problem the background
    # job manager solves, just less obviously, since a "foreground" command still isn't
    # guaranteed to be a single process.
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **pc.SUBPROCESS_TEXT_KWARGS,
            **pc.popen_kwargs_for_job(),
        )
    except OSError as e:
        return ToolResult(ok=False, error=f"Failed to run command: {e}")

    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        pc.kill_process_tree(proc.pid)
        try:
            proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            pc.force_kill_process_tree(proc.pid)
        return ToolResult(
            ok=False,
            error=(
                f"Command timed out after {timeout}s and was stopped, including anything it "
                f"spawned. If it's meant to keep running (a dev server, a watcher), start it "
                f"with background=true instead."
            ),
        )
    except Exception as e:
        return ToolResult(ok=False, error=f"Failed to run command: {e}")

    out = out or ""
    err = err or ""
    combined = out
    if err:
        combined += ("\n" if combined else "") + f"[stderr]\n{err}"
    combined = truncate_output(combined)

    ok = proc.returncode == 0
    return ToolResult(
        ok=ok,
        output=combined if ok else "",
        error="" if ok else (combined or f"exited with code {proc.returncode}"),
        meta={"returncode": proc.returncode},
    )


def run_command(command: str, cwd: str = None, timeout: int = 120, background: bool = False):
    if background:
        try:
            job = JOBS.start(command, cwd=cwd)
        except Exception as e:
            return ToolResult(ok=False, error=f"Could not start background job: {e}")
        time.sleep(0.4)  # let it produce a first line or fail fast, so we can report something useful
        if not job.running and job.returncode not in (0, None):
            return ToolResult(
                ok=False,
                error=f"{job.id} exited immediately with code {job.returncode}:\n{job.snapshot()}",
            )
        first = job.snapshot(tail=15).strip()
        body = f"Started {job.id} in the background: {command}"
        if first:
            body += f"\n\nFirst output:\n{first}"
        body += f"\n\nUse check_job('{job.id}') for more output, kill_job('{job.id}') to stop it."
        return ToolResult(ok=True, output=body, meta={"job_id": job.id, "background": True})

    args, use_shell = pc.build_shell_command(command)
    return _run(args, cwd=cwd, timeout=timeout, shell=use_shell)


def check_job(job_id: str, tail: int = 60):
    job = JOBS.get(job_id)
    if not job:
        known = ", ".join(j.id for j in JOBS.all()) or "none"
        return ToolResult(ok=False, error=f"No such job {job_id!r}. Known jobs: {known}")
    status = "running" if job.running else f"exited with code {job.returncode}"
    elapsed = time.time() - job.started
    out = job.snapshot(tail=tail).strip() or "(no output yet)"
    return ToolResult(
        ok=True,
        output=f"{job.id} [{status}, {elapsed:.0f}s]: {job.command}\n\n{truncate_output(out)}",
        meta={"running": job.running, "returncode": job.returncode},
    )


def kill_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return ToolResult(ok=False, error=f"No such job {job_id!r}")
    if not job.running:
        return ToolResult(ok=True, output=f"{job_id} had already exited (code {job.returncode})")
    if JOBS.kill(job_id):
        return ToolResult(ok=True, output=f"Stopped {job_id}: {job.command}")
    return ToolResult(ok=False, error=f"Could not stop {job_id}")


def list_jobs():
    jobs = JOBS.all()
    if not jobs:
        return ToolResult(ok=True, output="No background jobs.")
    lines = []
    for j in jobs:
        status = "running" if j.running else f"exited({j.returncode})"
        lines.append(f"{j.id:6} {status:14} {time.time() - j.started:5.0f}s  {j.command}")
    return ToolResult(ok=True, output="\n".join(lines))


def run_python(code: str, timeout: int = 60):
    return _run([sys.executable, "-c", code], timeout=timeout)
