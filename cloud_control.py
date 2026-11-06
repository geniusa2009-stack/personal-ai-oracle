"""Private cloud control plane for Personal AI Oracle.

The cloud never opens an inbound connection to the Mac. The Mac agent polls this
API over HTTPS and receives bounded, allow-listed jobs. Tokens are stored hashed.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import hashlib
import json
import os
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

MAX_JOB_BYTES = 32_768
MAX_RESULT_BYTES = 65_536
MAX_WAIT_SECONDS = 20
LEASE_SECONDS = 600
ALLOWED_REMOTE_TOOLS = {
    "local.list_directory",
    "local.read_file",
    "local.find_files",
    "web.search",
    "web.navigate",
    "web.extract",
    "web.links",
    "web.open_browser",
}

app = FastAPI(
    title="Personal AI Oracle Control Plane",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _db_path() -> Path:
    raw = os.environ.get("ORACLE_CLOUD_DB_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".personal_ai_oracle_cloud" / "control.db"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=15000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


@contextmanager
def _db_connection():
    connection = _connect()
    try:
        yield connection
    finally:
        connection.close()


def _bounded_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def init_db() -> None:
    with _db_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL,
                last_seen REAL NOT NULL,
                disabled INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                tool_id TEXT NOT NULL,
                tool_input TEXT NOT NULL,
                task TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                idempotency_key TEXT UNIQUE,
                device_id TEXT,
                lease_token_hash TEXT,
                lease_expires REAL,
                result_json TEXT,
                error TEXT,
                FOREIGN KEY(device_id) REFERENCES devices(device_id)
            );
            CREATE INDEX IF NOT EXISTS jobs_status_created
              ON jobs(status, created_at);
            CREATE INDEX IF NOT EXISTS jobs_device_status
              ON jobs(device_id, status);
            """
        )
        now = time.time()
        result_hours = _bounded_setting("ORACLE_CLOUD_RESULT_RETENTION_HOURS", 24, 1, 168)
        job_days = _bounded_setting("ORACLE_CLOUD_JOB_RETENTION_DAYS", 7, 1, 90)
        connection.execute(
            """UPDATE jobs SET result_json=NULL
               WHERE result_json IS NOT NULL AND status IN ('success','error','blocked')
               AND updated_at < ?""",
            (now - result_hours * 3600,),
        )
        connection.execute(
            """DELETE FROM jobs WHERE status IN ('success','error','blocked')
               AND created_at < ?""",
            (now - job_days * 86400,),
        )
    try:
        os.chmod(_db_path(), 0o600)
    except OSError:
        pass


def _secret(name: str, *, minimum: int = 32) -> str:
    value = os.environ.get(name, "")
    if len(value) < minimum:
        raise HTTPException(
            status_code=503,
            detail=f"Server configuration is missing or weak: {name}",
        )
    return value


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization[7:].strip()
    if not token or len(token) > 512:
        raise HTTPException(status_code=401, detail="Invalid bearer token")
    return token


def _require_control(authorization: str | None) -> None:
    supplied = _bearer(authorization)
    expected = _secret("ORACLE_CLOUD_CONTROL_TOKEN")
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid control token")


def _require_device(authorization: str | None) -> sqlite3.Row:
    supplied = _bearer(authorization)
    init_db()
    with _db_connection() as connection:
        row = connection.execute(
            "SELECT device_id, name FROM devices WHERE token_hash=? AND disabled=0",
            (_hash_token(supplied),),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Unknown or disabled device")
    return row


def _json_size(value: Any, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Payload must be JSON serializable") from exc
    if len(encoded.encode("utf-8")) > limit:
        raise HTTPException(status_code=413, detail="Payload is too large")
    return encoded


def _job_public(row: sqlite3.Row) -> dict[str, Any]:
    try:
        result = json.loads(row["result_json"]) if row["result_json"] else None
    except ValueError:
        result = None
    return {
        "job_id": row["job_id"],
        "tool_id": row["tool_id"],
        "task": row["task"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "device_id": row["device_id"],
        "result": result,
        "error": row["error"],
    }


@app.middleware("http")
async def request_size_guard(request: Request, call_next):
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_RESULT_BYTES + 4096:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
    return await call_next(request)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "oracle-control-plane"}


@app.post("/v1/devices/pair")
async def pair_device(
    request: Request,
    x_enrollment_token: str | None = Header(default=None),
) -> dict[str, str]:
    expected = _secret("ORACLE_CLOUD_ENROLLMENT_TOKEN")
    if not x_enrollment_token or not secrets.compare_digest(x_enrollment_token, expected):
        raise HTTPException(status_code=401, detail="Invalid enrollment token")
    body = await request.json()
    name = body.get("name", "Mac agent") if isinstance(body, dict) else "Mac agent"
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise HTTPException(status_code=422, detail="Device name must be 1-80 characters")
    device_id = str(uuid.uuid4())
    device_token = secrets.token_urlsafe(48)
    now = time.time()
    init_db()
    with _db_connection() as connection:
        connection.execute(
            "INSERT INTO devices(device_id,name,token_hash,created_at,last_seen) VALUES(?,?,?,?,?)",
            (device_id, name.strip(), _hash_token(device_token), now, now),
        )
    return {
        "device_id": device_id,
        "device_token": device_token,
        "message": "Store this token privately; it will not be shown again.",
    }


@app.post("/v1/jobs")
async def create_job(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_control(authorization)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="JSON object required")
    tool_id = body.get("tool_id")
    tool_input = body.get("input")
    task = body.get("task", "")
    idempotency_key = body.get("idempotency_key")
    if tool_id not in ALLOWED_REMOTE_TOOLS:
        raise HTTPException(status_code=422, detail="Remote tool is not enabled")
    if not isinstance(tool_input, dict):
        raise HTTPException(status_code=422, detail="input must be a JSON object")
    if not isinstance(task, str) or len(task) > 12000:
        raise HTTPException(status_code=422, detail="task must be at most 12000 characters")
    if idempotency_key is not None and (
        not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 120
    ):
        raise HTTPException(status_code=422, detail="Invalid idempotency key")
    input_json = _json_size(tool_input, MAX_JOB_BYTES)
    job_id = str(uuid.uuid4())
    now = time.time()
    init_db()
    with _db_connection() as connection:
        try:
            connection.execute(
                """INSERT INTO jobs(
                    job_id,tool_id,tool_input,task,status,created_at,updated_at,idempotency_key
                ) VALUES(?,?,?,?,?,?,?,?)""",
                (job_id, tool_id, input_json, task, "queued", now, now, idempotency_key),
            )
        except sqlite3.IntegrityError:
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=409, detail="Job could not be queued")
            return _job_public(row)
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs")
def list_jobs(
    limit: int = 50,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_control(authorization)
    limit = max(1, min(limit, 100))
    init_db()
    with _db_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"jobs": [_job_public(row) for row in rows]}


@app.get("/v1/jobs/{job_id}")
def get_job(
    job_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_control(authorization)
    init_db()
    with _db_connection() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_public(row)


@app.get("/v1/devices")
def list_devices(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_control(authorization)
    init_db()
    now = time.time()
    with _db_connection() as connection:
        rows = connection.execute(
            "SELECT device_id,name,created_at,last_seen,disabled FROM devices ORDER BY created_at"
        ).fetchall()
    return {
        "devices": [
            {
                "device_id": row["device_id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "last_seen": row["last_seen"],
                "online": not bool(row["disabled"]) and now - row["last_seen"] < 90,
                "disabled": bool(row["disabled"]),
            }
            for row in rows
        ]
    }


@app.post("/v1/devices/{device_id}/disable")
def disable_device(
    device_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _require_control(authorization)
    init_db()
    with _db_connection() as connection:
        changed = connection.execute(
            "UPDATE devices SET disabled=1 WHERE device_id=?", (device_id,)
        ).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "disabled"}


@app.post("/v1/agent/heartbeat")
def agent_heartbeat(
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    device = _require_device(authorization)
    with _db_connection() as connection:
        connection.execute(
            "UPDATE devices SET last_seen=? WHERE device_id=?",
            (time.time(), device["device_id"]),
        )
    return {"status": "ok"}


@app.get("/v1/agent/jobs/next")
async def next_job(
    wait_seconds: int = 20,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    device = _require_device(authorization)
    wait_seconds = max(0, min(wait_seconds, MAX_WAIT_SECONDS))
    deadline = time.monotonic() + wait_seconds
    while True:
        now = time.time()
        job = None
        lease_token = secrets.token_urlsafe(32)
        init_db()
        with _db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """UPDATE jobs SET status='queued',device_id=NULL,lease_token_hash=NULL,
                   lease_expires=NULL,updated_at=?
                   WHERE status='leased' AND lease_expires < ?""",
                (now, now),
            )
            row = connection.execute(
                "SELECT job_id,tool_id,tool_input,task FROM jobs "
                "WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is not None:
                changed = connection.execute(
                    """UPDATE jobs SET status='leased',device_id=?,lease_token_hash=?,
                       lease_expires=?,updated_at=?
                       WHERE job_id=? AND status='queued'""",
                    (
                        device["device_id"],
                        _hash_token(lease_token),
                        now + LEASE_SECONDS,
                        now,
                        row["job_id"],
                    ),
                ).rowcount
                if changed == 1:
                    job = dict(row)
                    job["input"] = json.loads(job.pop("tool_input"))
                    job["lease_token"] = lease_token
            connection.commit()
        if job is not None:
            with _db_connection() as connection:
                connection.execute(
                    "UPDATE devices SET last_seen=? WHERE device_id=?",
                    (time.time(), device["device_id"]),
                )
            return job
        if time.monotonic() >= deadline:
            return {"job": None}
        await asyncio.sleep(1)


@app.post("/v1/agent/jobs/{job_id}/result")
async def complete_job(
    job_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    device = _require_device(authorization)
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="JSON object required")
    lease_token = body.get("lease_token")
    status = body.get("status")
    if not isinstance(lease_token, str) or status not in {"success", "error", "blocked"}:
        raise HTTPException(status_code=422, detail="Invalid job result")
    result_json = _json_size(body.get("result", {}), MAX_RESULT_BYTES)
    now = time.time()
    init_db()
    with _db_connection() as connection:
        row = connection.execute(
            """SELECT lease_token_hash FROM jobs
               WHERE job_id=? AND device_id=? AND status='leased'""",
            (job_id, device["device_id"]),
        ).fetchone()
        if row is None or not secrets.compare_digest(
            row["lease_token_hash"] or "", _hash_token(lease_token)
        ):
            raise HTTPException(status_code=409, detail="Job lease is no longer valid")
        connection.execute(
            """UPDATE jobs SET status=?,result_json=?,updated_at=?,lease_token_hash=NULL,
               lease_expires=NULL WHERE job_id=? AND device_id=?""",
            (status, result_json, now, job_id, device["device_id"]),
        )
    return {"status": "recorded"}
