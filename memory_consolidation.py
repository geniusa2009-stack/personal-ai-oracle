"""Review-only memory consolidation candidate discovery.

This module detects potentially duplicate, related or contradictory memory
records. It never merges, overwrites, supersedes or deletes source memories.
All scans are deterministic, local and isolated to one memory scope.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Mapping

import memory
from database import init_database
from db import get_conn


ALGORITHM_VERSION = "lexical-review-v1"
MAX_SCOPE_LENGTH = 255
MAX_REASON_LENGTH = 1000
MAX_REVIEWER_LENGTH = 255
MAX_SIGNAL_TOKENS = 12
NEGATION_TOKENS = frozenset({
    "not", "no", "never", "without", "none", "neither", "cannot",
    "dont", "doesnt", "isnt", "wasnt", "wont", "can't", "don't",
    "doesn't", "مش", "مفيش", "ليس", "ليست", "لا", "لم", "لن", "غير", "ما",
})


class MemoryConsolidationError(ValueError):
    """Invalid consolidation scan, proposal or review operation."""


@dataclass(frozen=True)
class ConsolidationRun:
    run_id: str
    scope: str
    algorithm_version: str
    status: str
    scanned_count: int
    comparison_count: int
    proposal_count: int
    truncated: bool
    created_at: str
    finished_at: str | None


@dataclass(frozen=True)
class ConsolidationProposal:
    id: int
    scope: str
    proposal_type: str
    status: str
    similarity: float
    explanation: str
    signals: Mapping[str, Any]
    first_seen_at: str
    last_seen_at: str
    observation_count: int
    last_run_id: str
    reviewed_at: str | None
    reviewer: str | None
    review_reason: str | None
    member_ids: tuple[int, ...]
    member_content_hashes: tuple[str, ...]
    members: tuple[memory.MemoryRecord, ...]
    stale_member_ids: tuple[int, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _scope(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_SCOPE_LENGTH:
        raise MemoryConsolidationError("scope is required and must be at most 255 characters")
    return value.strip()


def _text(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MemoryConsolidationError(f"{field} is required")
    value = value.strip()
    if len(value) > maximum:
        raise MemoryConsolidationError(f"{field} must be at most {maximum} characters")
    return value


def _positive_id(value: Any, field: str = "proposal_id") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MemoryConsolidationError(f"{field} must be a positive integer")
    return value


def _bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MemoryConsolidationError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _threshold(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MemoryConsolidationError(f"{field} must be a finite number from 0 to 1")
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise MemoryConsolidationError(f"{field} must be a finite number from 0 to 1")
    return result


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_active_and_valid(row: Any, now: datetime) -> bool:
    status = row["metadata_status"] or "active"
    if status != "active":
        return False
    start = _parse_time(row["valid_from"])
    end = _parse_time(row["valid_until"])
    return (start is None or start <= now) and (end is None or end >= now)


def _tokens(text: str) -> set[str]:
    return memory._memory_tokens(text)


def _numeric_values(text: str) -> set[str]:
    values: set[str] = set()
    for raw in re.findall(r"(?<!\w)\d+(?:[.,]\d+)?", text):
        normalized = []
        for char in raw:
            try:
                normalized.append(str(unicodedata.digit(char)))
            except (TypeError, ValueError):
                normalized.append(char)
        values.add("".join(normalized).replace(",", "."))
    return values


def _similarity(left: set[str], right: set[str]) -> tuple[float, float, set[str]]:
    shared = left & right
    if not left or not right:
        return 0.0, 0.0, shared
    cosine = len(shared) / math.sqrt(len(left) * len(right))
    jaccard = len(shared) / len(left | right)
    return cosine, jaccard, shared


def _classify_pair(
    left: Any,
    right: Any,
    *,
    duplicate_threshold: float,
    related_threshold: float,
    contradiction_threshold: float,
    min_shared_tokens: int,
) -> tuple[str, float, dict[str, Any], str] | None:
    left_tokens = _tokens(left["content"])
    right_tokens = _tokens(right["content"])
    cosine, jaccard, shared = _similarity(left_tokens, right_tokens)
    if len(shared) < min_shared_tokens:
        return None

    left_negations = left_tokens & NEGATION_TOKENS
    right_negations = right_tokens & NEGATION_TOKENS
    polarity_mismatch = left_negations != right_negations

    left_numbers = _numeric_values(left["content"])
    right_numbers = _numeric_values(right["content"])
    numeric_mismatch = bool(left_numbers and right_numbers and left_numbers != right_numbers)

    shared_non_numeric = {
        token for token in shared if not any(char.isdigit() for char in token)
    }
    left_non_numeric = {
        token for token in left_tokens if not any(char.isdigit() for char in token)
    }
    right_non_numeric = {
        token for token in right_tokens if not any(char.isdigit() for char in token)
    }
    context_jaccard = (
        len(shared_non_numeric) / len(left_non_numeric | right_non_numeric)
        if left_non_numeric and right_non_numeric
        else 0.0
    )

    conflict_signals = []
    if polarity_mismatch:
        conflict_signals.append("negation_mismatch")
    if numeric_mismatch:
        conflict_signals.append("numeric_values_differ")

    if conflict_signals and cosine >= contradiction_threshold and context_jaccard >= 0.4:
        proposal_type = "potential_contradiction"
        explanation = (
            "These records share key terms but differ in negation or numeric values. "
            "This is a review signal, not a verified contradiction."
        )
    elif cosine >= duplicate_threshold or jaccard >= duplicate_threshold:
        proposal_type = "potential_duplicate"
        explanation = (
            "These records have high lexical overlap and may describe the same memory. "
            "Review wording, dates and provenance before deciding."
        )
    elif cosine >= related_threshold:
        proposal_type = "related"
        explanation = (
            "These records share several meaningful terms and may belong to the same topic. "
            "No merge or conflict is inferred."
        )
    else:
        return None

    signals = {
        "cosine_similarity": round(cosine, 6),
        "jaccard_similarity": round(jaccard, 6),
        "shared_token_count": len(shared),
        "shared_tokens": sorted(shared)[:MAX_SIGNAL_TOKENS],
        "left_memory_type": left["memory_type"],
        "right_memory_type": right["memory_type"],
        "left_source": left["source"],
        "right_source": right["source"],
        "left_negation_tokens": sorted(left_negations),
        "right_negation_tokens": sorted(right_negations),
        "left_numeric_values": sorted(left_numbers),
        "right_numeric_values": sorted(right_numbers),
        "conflict_signals": conflict_signals,
    }
    return proposal_type, cosine, signals, explanation


def _proposal_key(
    scope: str,
    proposal_type: str,
    members: list[Any],
) -> tuple[str, list[tuple[int, str]]]:
    member_versions = sorted(
        (int(row["id"]), _content_hash(row["content"]))
        for row in members
    )
    source = json.dumps(
        [scope, ALGORITHM_VERSION, proposal_type, member_versions],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest(), member_versions


def _persist_proposal(
    conn: Any,
    *,
    scope: str,
    run_id: str,
    proposal_type: str,
    members: list[Any],
    similarity: float,
    signals: Mapping[str, Any],
    explanation: str,
    now: str,
) -> tuple[int, bool]:
    key, versions = _proposal_key(scope, proposal_type, members)
    signals_json = json.dumps(
        dict(signals), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    cursor = conn.execute(
        """INSERT OR IGNORE INTO memory_consolidation_proposals
           (scope,proposal_key,proposal_type,status,similarity,explanation,signals_json,
            first_seen_at,last_seen_at,observation_count,last_run_id)
           VALUES(?,?,?,'pending_review',?,?,?,?,?,1,?)""",
        (scope, key, proposal_type, similarity, explanation, signals_json, now, now, run_id),
    )
    row = conn.execute(
        """SELECT id FROM memory_consolidation_proposals
           WHERE scope=? AND proposal_key=?""",
        (scope, key),
    ).fetchone()
    if row is None:
        raise MemoryConsolidationError("proposal could not be persisted")
    proposal_id = int(row["id"])
    created = cursor.rowcount == 1
    conn.execute(
        """UPDATE memory_consolidation_proposals
           SET similarity=?,explanation=?,signals_json=?,last_seen_at=?,
               observation_count=observation_count+?,last_run_id=?
           WHERE id=? AND scope=?""",
        (
            similarity, explanation, signals_json, now,
            0 if created else 1, run_id, proposal_id, scope,
        ),
    )
    for memory_id, digest in versions:
        conn.execute(
            """INSERT OR IGNORE INTO memory_consolidation_proposal_members
               (proposal_id,memory_id,scope,content_hash)
               VALUES(?,?,?,?)""",
            (proposal_id, memory_id, scope, digest),
        )
    conn.execute(
        """INSERT OR IGNORE INTO memory_consolidation_observations
           (run_id,proposal_id,scope,similarity,signals_json,observed_at)
           VALUES(?,?,?,?,?,?)""",
        (run_id, proposal_id, scope, similarity, signals_json, now),
    )
    return proposal_id, created


def scan_scope(
    scope: str,
    *,
    candidate_limit: int = 200,
    max_pair_checks: int = 20000,
    max_proposals: int = 500,
    duplicate_threshold: float = 0.84,
    related_threshold: float = 0.60,
    contradiction_threshold: float = 0.58,
    min_shared_tokens: int = 2,
) -> ConsolidationRun:
    """Scan active memories and persist review proposals; never mutate memories."""
    scope = _scope(scope)
    candidate_limit = _bounded_int(candidate_limit, "candidate_limit", 2, 500)
    max_pair_checks = _bounded_int(max_pair_checks, "max_pair_checks", 1, 50000)
    max_proposals = _bounded_int(max_proposals, "max_proposals", 1, 1000)
    duplicate_threshold = _threshold(duplicate_threshold, "duplicate_threshold")
    related_threshold = _threshold(related_threshold, "related_threshold")
    contradiction_threshold = _threshold(contradiction_threshold, "contradiction_threshold")
    min_shared_tokens = _bounded_int(min_shared_tokens, "min_shared_tokens", 1, 20)
    if related_threshold > duplicate_threshold:
        raise MemoryConsolidationError("related_threshold cannot exceed duplicate_threshold")

    run_id = uuid.uuid4().hex
    now = _now()
    parameters = {
        "candidate_limit": candidate_limit,
        "max_pair_checks": max_pair_checks,
        "max_proposals": max_proposals,
        "duplicate_threshold": duplicate_threshold,
        "related_threshold": related_threshold,
        "contradiction_threshold": contradiction_threshold,
        "min_shared_tokens": min_shared_tokens,
    }

    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            """SELECT m.id,m.content,m.memory_type,m.scope,m.source,m.created_at,
                      md.confidence,md.importance,md.valid_from,md.valid_until,
                      md.status AS metadata_status
               FROM memories AS m
               LEFT JOIN memory_metadata AS md
                 ON md.memory_id=m.id AND md.scope=m.scope
               WHERE m.scope=?
               ORDER BY m.created_at DESC,m.id DESC LIMIT ?""",
            (scope, candidate_limit),
        ).fetchall()
        current = datetime.now(timezone.utc)
        candidates = [
            row for row in rows
            if _is_active_and_valid(row, current)
            and len(_tokens(row["content"])) >= min_shared_tokens
        ]

        conn.execute(
            """INSERT INTO memory_consolidation_runs
               (run_id,scope,algorithm_version,status,scanned_count,comparison_count,
                proposal_count,truncated,parameters_json,created_at,finished_at)
               VALUES(?,?,?,'completed',0,0,0,0,?,?,NULL)""",
            (
                run_id, scope, ALGORITHM_VERSION,
                json.dumps(parameters, sort_keys=True, separators=(",", ":")),
                now,
            ),
        )

        comparisons = 0
        proposals_created = 0
        proposals_observed = 0
        truncated = len(rows) >= candidate_limit
        by_type: dict[str, list[Any]] = {}
        for row in candidates:
            by_type.setdefault(row["memory_type"], []).append(row)

        found: list[tuple[str, list[Any], float, dict[str, Any], str]] = []
        stop = False
        for group in by_type.values():
            for left, right in combinations(group, 2):
                if comparisons >= max_pair_checks:
                    truncated = True
                    stop = True
                    break
                comparisons += 1
                candidate = _classify_pair(
                    left,
                    right,
                    duplicate_threshold=duplicate_threshold,
                    related_threshold=related_threshold,
                    contradiction_threshold=contradiction_threshold,
                    min_shared_tokens=min_shared_tokens,
                )
                if candidate is None:
                    continue
                proposal_type, similarity, signals, explanation = candidate
                found.append((proposal_type, [left, right], similarity, signals, explanation))
                if len(found) >= max_proposals:
                    truncated = True
                    stop = True
                    break
            if stop:
                break

        for proposal_type, members, similarity, signals, explanation in found:
            _proposal_id, created = _persist_proposal(
                conn,
                scope=scope,
                run_id=run_id,
                proposal_type=proposal_type,
                members=members,
                similarity=similarity,
                signals=signals,
                explanation=explanation,
                now=now,
            )
            proposals_created += int(created)
            proposals_observed += 1

        finished = _now()
        status = "partial" if truncated else "completed"
        conn.execute(
            """UPDATE memory_consolidation_runs
               SET status=?,scanned_count=?,comparison_count=?,proposal_count=?,
                   truncated=?,finished_at=?
               WHERE run_id=? AND scope=?""",
            (
                status, len(candidates), comparisons, proposals_observed,
                int(truncated), finished, run_id, scope,
            ),
        )
        conn.commit()
        return ConsolidationRun(
            run_id=run_id,
            scope=scope,
            algorithm_version=ALGORITHM_VERSION,
            status=status,
            scanned_count=len(candidates),
            comparison_count=comparisons,
            proposal_count=proposals_observed,
            truncated=truncated,
            created_at=now,
            finished_at=finished,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _proposal_from_conn(conn: Any, proposal_id: int, scope: str) -> ConsolidationProposal | None:
    row = conn.execute(
        """SELECT id,scope,proposal_type,status,similarity,explanation,signals_json,
                  first_seen_at,last_seen_at,observation_count,last_run_id,
                  reviewed_at,reviewer,review_reason
           FROM memory_consolidation_proposals WHERE id=? AND scope=?""",
        (proposal_id, scope),
    ).fetchone()
    if row is None:
        return None
    member_rows = conn.execute(
        """SELECT memory_id,content_hash FROM memory_consolidation_proposal_members
           WHERE proposal_id=? AND scope=? ORDER BY memory_id""",
        (proposal_id, scope),
    ).fetchall()
    member_ids = tuple(int(item["memory_id"]) for item in member_rows)
    hashes = tuple(item["content_hash"] for item in member_rows)
    current_records = []
    stale_ids = []
    for item in member_rows:
        source_row = conn.execute(
            """SELECT id,content,memory_type,scope,source,created_at
               FROM memories WHERE id=? AND scope=?""",
            (item["memory_id"], scope),
        ).fetchone()
        if source_row is None or _content_hash(source_row["content"]) != item["content_hash"]:
            stale_ids.append(int(item["memory_id"]))
            continue
        metadata = conn.execute(
            "SELECT status FROM memory_metadata WHERE memory_id=? AND scope=?",
            (item["memory_id"], scope),
        ).fetchone()
        if metadata is not None and metadata["status"] != "active":
            stale_ids.append(int(item["memory_id"]))
            continue
        current_records.append(memory._record_from_row(source_row))
    try:
        signals = json.loads(row["signals_json"])
    except (TypeError, ValueError):
        signals = {}
    return ConsolidationProposal(
        id=int(row["id"]), scope=row["scope"], proposal_type=row["proposal_type"],
        status=row["status"], similarity=float(row["similarity"]),
        explanation=row["explanation"],
        signals=signals if isinstance(signals, dict) else {},
        first_seen_at=row["first_seen_at"], last_seen_at=row["last_seen_at"],
        observation_count=int(row["observation_count"]), last_run_id=row["last_run_id"],
        reviewed_at=row["reviewed_at"], reviewer=row["reviewer"],
        review_reason=row["review_reason"],
        member_ids=member_ids, member_content_hashes=hashes,
        members=tuple(current_records), stale_member_ids=tuple(stale_ids),
    )


def get_proposal(scope: str, proposal_id: int) -> ConsolidationProposal | None:
    scope = _scope(scope)
    proposal_id = _positive_id(proposal_id)
    init_database()
    conn = get_conn()
    try:
        return _proposal_from_conn(conn, proposal_id, scope)
    finally:
        conn.close()


def list_proposals(
    scope: str,
    *,
    status: str | None = "pending_review",
    proposal_type: str | None = None,
    limit: int = 100,
) -> list[ConsolidationProposal]:
    scope = _scope(scope)
    limit = _bounded_int(limit, "limit", 1, 500)
    if status is not None and status not in {"pending_review", "accepted", "dismissed", "stale"}:
        raise MemoryConsolidationError("unsupported proposal status")
    if proposal_type is not None and proposal_type not in {
        "potential_duplicate", "potential_contradiction", "related"
    }:
        raise MemoryConsolidationError("unsupported proposal type")

    clauses = ["scope=?"]
    parameters: list[Any] = [scope]
    if status == "stale":
        clauses.append("(status='stale' OR status='pending_review')")
    elif status is not None:
        clauses.append("status=?")
        parameters.append(status)
    if proposal_type is not None:
        clauses.append("proposal_type=?")
        parameters.append(proposal_type)
    parameters.append(limit)

    init_database()
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT id FROM memory_consolidation_proposals WHERE """
            + " AND ".join(clauses)
            + " ORDER BY last_seen_at DESC,id DESC LIMIT ?",
            parameters,
        ).fetchall()
        proposals = [
            _proposal_from_conn(conn, int(row["id"]), scope)
            for row in rows
        ]
        result = [proposal for proposal in proposals if proposal is not None]
        if status == "stale":
            return [
                proposal for proposal in result
                if proposal.status == "stale" or proposal.stale_member_ids
            ]
        return result
    finally:
        conn.close()


def review_proposal(
    scope: str,
    proposal_id: int,
    *,
    decision: str,
    reviewer: str,
    reason: str,
) -> ConsolidationProposal:
    """Accept/dismiss a proposal only; no source memory is changed."""
    scope = _scope(scope)
    proposal_id = _positive_id(proposal_id)
    reviewer = _text(reviewer, "reviewer", MAX_REVIEWER_LENGTH)
    reason = _text(reason, "reason", MAX_REASON_LENGTH)
    if decision not in {"accepted", "dismissed"}:
        raise MemoryConsolidationError("decision must be accepted or dismissed")

    init_database()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        proposal = conn.execute(
            """SELECT id,status FROM memory_consolidation_proposals
               WHERE id=? AND scope=?""",
            (proposal_id, scope),
        ).fetchone()
        if proposal is None:
            raise MemoryConsolidationError("proposal was not found in the supplied scope")
        if proposal["status"] != "pending_review":
            raise MemoryConsolidationError("only pending proposals can be reviewed")

        member_rows = conn.execute(
            """SELECT memory_id,content_hash FROM memory_consolidation_proposal_members
               WHERE proposal_id=? AND scope=?""",
            (proposal_id, scope),
        ).fetchall()
        now = _now()
        stale = len(member_rows) < 2
        for item in member_rows:
            row = conn.execute(
                """SELECT m.content,md.status AS metadata_status
                   FROM memories AS m
                   LEFT JOIN memory_metadata AS md
                     ON md.memory_id=m.id AND md.scope=m.scope
                   WHERE m.id=? AND m.scope=?""",
                (item["memory_id"], scope),
            ).fetchone()
            if (
                row is None
                or _content_hash(row["content"]) != item["content_hash"]
                or (row["metadata_status"] or "active") != "active"
            ):
                stale = True
                break

        if stale:
            conn.execute(
                """UPDATE memory_consolidation_proposals
                   SET status='stale',reviewed_at=?,reviewer='system',
                       review_reason='Source memories changed or are no longer active'
                   WHERE id=? AND scope=?""",
                (now, proposal_id, scope),
            )
        else:
            conn.execute(
                """UPDATE memory_consolidation_proposals
                   SET status=?,reviewed_at=?,reviewer=?,review_reason=?
                   WHERE id=? AND scope=?""",
                (decision, now, reviewer, reason, proposal_id, scope),
            )
        conn.commit()
        return get_proposal(scope, proposal_id)  # type: ignore[return-value]
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_run(scope: str, run_id: str) -> ConsolidationRun | None:
    scope = _scope(scope)
    run_id = _text(run_id, "run_id", 64)
    init_database()
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT run_id,scope,algorithm_version,status,scanned_count,
                      comparison_count,proposal_count,truncated,created_at,finished_at
               FROM memory_consolidation_runs WHERE run_id=? AND scope=?""",
            (run_id, scope),
        ).fetchone()
        if row is None:
            return None
        return ConsolidationRun(
            run_id=row["run_id"], scope=row["scope"],
            algorithm_version=row["algorithm_version"], status=row["status"],
            scanned_count=int(row["scanned_count"]),
            comparison_count=int(row["comparison_count"]),
            proposal_count=int(row["proposal_count"]),
            truncated=bool(row["truncated"]),
            created_at=row["created_at"], finished_at=row["finished_at"],
        )
    finally:
        conn.close()
