"""`geo-gateway serve` - starts the Gateway daemon (FastAPI app in server.py)
via uvicorn. This is the one new entry point the gateway adds; the existing
terminal CLI/TUI (`geo`) is untouched and lives entirely in geocentric/cli.py.
"""
from __future__ import annotations

import argparse
import webbrowser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geo-gateway")
    sub = p.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="start the Gateway daemon and web chat")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8420)
    serve.add_argument("--open", action="store_true", help="open the web chat in a browser once the server is up")
    serve.add_argument("--reload", action="store_true", help="auto-reload on code changes (development only)")

    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        import threading
        import time

        import uvicorn

        if args.open:
            def _open_when_ready():
                time.sleep(1.0)
                webbrowser.open(f"http://{args.host}:{args.port}/")

            threading.Thread(target=_open_when_ready, daemon=True).start()

        uvicorn.run(
            "geocentric_gateway.server:app",
            host=args.host, port=args.port, reload=args.reload,
        )


if __name__ == "__main__":
    main()
