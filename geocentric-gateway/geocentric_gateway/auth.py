"""Stub single-local-user auth.

This is a localhost daemon for one person - OpenClaw itself is explicitly a
"single-operator" system, and there's nothing to authenticate against here.
Login/signup always succeed and hand back a fixed identity; the frontend's
account chip, chat sync, and cron-job endpoints just need *some* truthy
token/user to work with (see the LOCAL_TOKEN default patched into
web/index.html's initial state).
"""
from __future__ import annotations

LOCAL_TOKEN = "local"
LOCAL_USER = {"name": "You", "email": "local@geocentric"}


def login(_body: dict) -> dict:
    return {"token": LOCAL_TOKEN, "user": LOCAL_USER}


def signup(body: dict) -> dict:
    name = (body.get("name") or "").strip() or LOCAL_USER["name"]
    return {"token": LOCAL_TOKEN, "user": {**LOCAL_USER, "name": name}}
