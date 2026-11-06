"""Privacy-safe model execution metrics; prompts and completions are never stored."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import math
import re
from typing import Any

from database import init_database
from db import get_conn

MAX_EVENTS = 5000


def _scope(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()) or len(value) > 255:
        raise ValueError("A valid owner scope is required.")
    return value


def record_event(
    *,
    scope: str,
    provider: str,
    model: str,
    route_reason: str,
    latency_ms: int,
    outcome: str,
    output_chars: int = 0,
) -> None:
    """Persist only bounded routing/latency metadata, never message content."""
    try:
        scope = _scope(scope)
        provider = re.sub(r"[^A-Za-z0-9_.-]", "_", str(provider))[:80]
        model = re.sub(r"[^A-Za-z0-9_./:-]", "_", str(model))[:160]
        route_reason = re.sub(r"[^A-Za-z0-9_.:-]", "_", str(route_reason))[:80]
        if isinstance(latency_ms, bool) or not isinstance(latency_ms, int) or latency_ms < 0:
            return
        if outcome not in {"success", "error", "cancelled"}:
            return
        if isinstance(output_chars, bool) or not isinstance(output_chars, int) or output_chars < 0:
            return
        init_database()
        conn = get_conn()
        try:
            conn.execute(
                """INSERT INTO oracle_model_events
                   (scope,provider,model,route_reason,latency_ms,outcome,output_chars,created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    scope, provider, model, route_reason, latency_ms, outcome,
                    min(output_chars, 10_000_000),
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            conn.execute(
                """DELETE FROM oracle_model_events WHERE scope=? AND id NOT IN
                   (SELECT id FROM oracle_model_events WHERE scope=? ORDER BY id DESC LIMIT ?)""",
                (scope, scope, MAX_EVENTS),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        # Observability must never break a user task.
        return


def list_events(scope: str, *, limit: int = 100) -> list[dict[str, Any]]:
    scope = _scope(scope)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000.")
    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT provider,model,route_reason,latency_ms,outcome,output_chars,created_at
               FROM oracle_model_events WHERE scope=? ORDER BY id DESC LIMIT ?""",
            (scope, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _percentile(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    if not ordered:
        return 0
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def summary(scope: str, *, limit: int = 1000) -> list[dict[str, Any]]:
    """Summarize recent provider/model health without revealing prompts or answers."""
    events = list_events(scope, limit=limit)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[(event["provider"], event["model"])].append(event)
    result = []
    for (provider, model), rows in sorted(grouped.items()):
        latencies = [int(row["latency_ms"]) for row in rows]
        successes = sum(row["outcome"] == "success" for row in rows)
        errors = sum(row["outcome"] == "error" for row in rows)
        result.append({
            "provider": provider,
            "model": model,
            "requests": len(rows),
            "success_rate": round(successes / len(rows), 3),
            "errors": errors,
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
        })
    return result
