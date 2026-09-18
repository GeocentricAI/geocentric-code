"""Two-Mac linking: LAN discovery, pairing, and (once paired) either handing
inference to an `exo` cluster or delegating whole tasks to the paired peer's
own agent.

No new dependencies - discovery is a plain UDP broadcast, pairing and task
delegation run over one persistent newline-delimited-JSON TCP connection per
peer, deliberately mirroring the stdin/stdout protocol gui_bridge.py already
speaks with the Swift shell. Nothing here talks to exo directly; that's
cluster_mode.py's job once two machines are paired.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

DISCOVERY_PORT = 52321
CONTROL_PORT = 52322
BROADCAST_INTERVAL = 2.0
PEER_TIMEOUT = 7.0  # a peer not heard from in this long is dropped from the list
TASK_TIMEOUT = 600  # seconds a delegated task may run before the caller gives up


@dataclass
class Peer:
    id: str
    name: str
    address: str
    tcp_port: int = CONTROL_PORT
    last_seen: float = field(default_factory=time.time)
    paired: bool = False


class ClusterNode:
    """One machine's side of a link. `on_event` receives the same kind of
    dicts Agent/Runner emit - the GUI bridge just forwards them."""

    def __init__(
        self, on_event: Callable[[dict], None], on_delegate_task: Callable[[str], str],
        discovery_port: int = DISCOVERY_PORT, control_port: int = CONTROL_PORT,
    ):
        self.id = uuid.uuid4().hex[:12]
        self.name = socket.gethostname().split(".")[0]
        self.on_event = on_event
        self.on_delegate_task = on_delegate_task
        # Overridable only for tests exercising two nodes on one host - real
        # linking always uses the well-known defaults on both machines.
        self.discovery_port = discovery_port
        self.control_port = control_port

        self.mode: Optional[str] = None  # None | "cluster" | "orchestration"
        self.peers: dict[str, Peer] = {}
        self._paired_peer: Optional[Peer] = None
        self._paired_sock: Optional[socket.socket] = None
        self._paired_lock = threading.Lock()

        self._linking = False
        self._threads: list[threading.Thread] = []
        self._pending_results: dict[str, threading.Event] = {}
        self._pending_payloads: dict[str, dict] = {}

    # ------------------------------------------------------------------ linking

    def start_linking(self) -> None:
        if self._linking:
            return
        self._linking = True
        self.peers.clear()
        for target in (self._run_broadcaster, self._run_discovery_listener, self._run_control_server, self._run_prune_loop):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        self._emit({"type": "cluster_linking_started", "id": self.id, "name": self.name})

    def stop_linking(self) -> None:
        self._linking = False
        with self._paired_lock:
            if self._paired_sock:
                try:
                    self._paired_sock.close()
                except OSError:
                    pass
            self._paired_sock = None
            self._paired_peer = None
        self.peers.clear()
        self.mode = None
        self._emit({"type": "cluster_linking_stopped"})

    def _emit(self, event: dict) -> None:
        try:
            self.on_event(event)
        except Exception:
            pass

    # ------------------------------------------------------------------ discovery

    def _run_broadcaster(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({
            "type": "geocentric_peer", "id": self.id, "name": self.name, "tcp_port": self.control_port,
        }).encode("utf-8")
        while self._linking:
            try:
                sock.sendto(payload, ("255.255.255.255", self.discovery_port))
            except OSError:
                pass
            time.sleep(BROADCAST_INTERVAL)
        sock.close()

    def _run_discovery_listener(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(1.0)
        try:
            sock.bind(("", self.discovery_port))
        except OSError as e:
            self._emit({"type": "error", "message": f"cluster discovery couldn't bind: {e}"})
            return
        while self._linking:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if msg.get("type") != "geocentric_peer" or msg.get("id") == self.id:
                continue
            peer_id = msg.get("id")
            is_new = peer_id not in self.peers
            self.peers[peer_id] = Peer(
                id=peer_id, name=msg.get("name", "Unknown Mac"), address=addr[0],
                tcp_port=int(msg.get("tcp_port", self.control_port)),
                paired=self.peers.get(peer_id).paired if peer_id in self.peers else False,
            )
            if is_new:
                self._emit({
                    "type": "cluster_peer_found", "id": peer_id,
                    "name": self.peers[peer_id].name, "address": addr[0],
                })
        sock.close()

    def _run_prune_loop(self) -> None:
        while self._linking:
            time.sleep(2.0)
            cutoff = time.time() - PEER_TIMEOUT
            gone = [pid for pid, p in self.peers.items() if p.last_seen < cutoff and not p.paired]
            for pid in gone:
                del self.peers[pid]
                self._emit({"type": "cluster_peer_lost", "id": pid})

    # ------------------------------------------------------------------ pairing

    def request_pairing(self, peer_id: str) -> None:
        peer = self.peers.get(peer_id)
        if not peer:
            return
        try:
            sock = socket.create_connection((peer.address, peer.tcp_port), timeout=5)
            self._send(sock, {"type": "pair_request", "id": self.id, "name": self.name})
            reply = self._recv(sock, timeout=15)
        except OSError as e:
            self._emit({"type": "error", "message": f"Couldn't reach {peer.name}: {e}"})
            return
        if reply and reply.get("type") == "pair_accept":
            self._adopt_pairing(peer, sock)
        else:
            self._emit({"type": "cluster_pair_declined", "id": peer_id})
            sock.close()

    def _adopt_pairing(self, peer: Peer, sock: socket.socket) -> None:
        peer.paired = True
        with self._paired_lock:
            self._paired_peer = peer
            self._paired_sock = sock
        t = threading.Thread(target=self._run_peer_reader, args=(sock,), daemon=True)
        t.start()
        self._threads.append(t)
        self._emit({"type": "cluster_paired", "id": peer.id, "name": peer.name})

    def _run_control_server(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("", self.control_port))
            srv.listen(2)
            srv.settimeout(1.0)
        except OSError as e:
            self._emit({"type": "error", "message": f"cluster control port unavailable: {e}"})
            return
        while self._linking:
            try:
                conn, addr = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            first = self._recv(conn, timeout=10)
            if not first or first.get("type") != "pair_request":
                conn.close()
                continue
            peer = Peer(id=first["id"], name=first.get("name", "Unknown Mac"), address=addr[0])
            self.peers[peer.id] = peer
            # Surfaced to the user as an incoming request; the GUI decides
            # accept/decline and calls back through answer_pairing().
            self._pending_payloads[peer.id] = {"sock": conn}
            self._emit({"type": "cluster_pair_incoming", "id": peer.id, "name": peer.name, "address": addr[0]})
        srv.close()

    def answer_pairing(self, peer_id: str, accept: bool) -> None:
        pending = self._pending_payloads.pop(peer_id, None)
        if not pending:
            return
        sock: socket.socket = pending["sock"]
        peer = self.peers.get(peer_id)
        if accept and peer:
            self._send(sock, {"type": "pair_accept", "id": self.id, "name": self.name})
            self._adopt_pairing(peer, sock)
        else:
            self._send(sock, {"type": "pair_decline"})
            sock.close()

    def set_mode(self, mode: Optional[str]) -> None:
        if mode not in (None, "cluster", "orchestration"):
            return
        if mode is not None and self._paired_peer is None:
            self._emit({"type": "error", "message": "Pair with a Mac before choosing a mode."})
            return
        self.mode = mode
        self._emit({"type": "cluster_mode_changed", "mode": mode or ""})

    # ------------------------------------------------------------------ task delegation (orchestration mode)

    def delegate(self, task: str) -> str:
        """Blocks the calling thread (a tool call, already off the main loop)
        until the peer finishes the task or TASK_TIMEOUT elapses."""
        with self._paired_lock:
            sock = self._paired_sock
        if sock is None:
            return "ERROR: not paired with another Mac."
        task_id = uuid.uuid4().hex[:8]
        event = threading.Event()
        self._pending_results[task_id] = event
        self._send(sock, {"type": "delegate_task", "task_id": task_id, "task": task})
        if not event.wait(timeout=TASK_TIMEOUT):
            self._pending_results.pop(task_id, None)
            return "ERROR: the other Mac didn't respond in time."
        result = self._pending_payloads.pop(task_id, {}).get("result", "")
        return result

    def _run_peer_reader(self, sock: socket.socket) -> None:
        buf = b""
        while self._linking:
            try:
                chunk = sock.recv(65536)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                self._handle_peer_message(sock, msg)
        with self._paired_lock:
            if self._paired_sock is sock:
                name = self._paired_peer.name if self._paired_peer else "the other Mac"
                self._paired_sock = None
                self._paired_peer = None
                self.mode = None
                self._emit({"type": "cluster_unpaired", "name": name})

    def _handle_peer_message(self, sock: socket.socket, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "delegate_task":
            task_id = msg.get("task_id", "")
            task = msg.get("task", "")
            self._emit({"type": "cluster_task_received", "task_id": task_id, "task": task})

            def run_and_reply():
                result = self.on_delegate_task(task)
                self._send(sock, {"type": "task_result", "task_id": task_id, "result": result})
                self._emit({"type": "cluster_task_finished", "task_id": task_id})

            threading.Thread(target=run_and_reply, daemon=True).start()
        elif kind == "task_result":
            task_id = msg.get("task_id", "")
            self._pending_payloads[task_id] = {"result": msg.get("result", "")}
            ev = self._pending_results.pop(task_id, None)
            if ev:
                ev.set()

    # ------------------------------------------------------------------ wire helpers

    @staticmethod
    def _send(sock: socket.socket, payload: dict) -> None:
        try:
            sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        except OSError:
            pass

    @staticmethod
    def _recv(sock: socket.socket, timeout: float) -> Optional[dict]:
        sock.settimeout(timeout)
        buf = b""
        try:
            while b"\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    return None
                buf += chunk
        except OSError:
            return None
        line = buf.split(b"\n", 1)[0]
        try:
            return json.loads(line.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
