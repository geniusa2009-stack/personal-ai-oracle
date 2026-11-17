"""Bounded owner-scoped metadata in Oracle's existing SQLite database."""
from datetime import datetime, timezone
import json
import re
from db import get_conn

MAX_EVENTS = 200
LABELS = {'SUPPORTED', 'CONTRADICTED', 'CONFLICTING_EVIDENCE', 'INSUFFICIENT_EVIDENCE', 'UNVERIFIED'}


def _scope(scope):
    if not isinstance(scope, str) or not scope.strip() or len(scope) > 255:
        raise ValueError('explicit scope required')
    return scope.strip()


def _schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS oracle_local_ai_events (
        id INTEGER PRIMARY KEY, scope TEXT NOT NULL, workload TEXT NOT NULL,
        phase TEXT NOT NULL, model TEXT NOT NULL, created_at TEXT NOT NULL,
        counts_json TEXT NOT NULL, latency_ms INTEGER NOT NULL, error_category TEXT)''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_local_ai_scope ON oracle_local_ai_events(scope,id)')


def record(scope, workload, phase, model, *, counts=None, latency_ms=0, error=None):
    scope = _scope(scope)
    if workload not in {'indexing', 'verification'} or phase not in {'start', 'end'}:
        raise ValueError('invalid event kind')
    allowed = LABELS | {'indexed_count', 'skipped_count', 'failed_count'}
    clean = {k: min(v, 100000) for k,v in (counts or {}).items() if k in allowed and isinstance(v, int) and not isinstance(v, bool) and v >= 0}
    category = error if error in {'resource', 'runtime', 'configuration'} else None
    # Model IDs only; never accept provider response or error text.
    identity = re.sub(r'[^A-Za-z0-9_./:-]', '_', str(model))[:160]
    conn = get_conn()
    try:
        with conn:
            _schema(conn)
            conn.execute('INSERT INTO oracle_local_ai_events(scope,workload,phase,model,created_at,counts_json,latency_ms,error_category) VALUES(?,?,?,?,?,?,?,?)', (scope,workload,phase,identity,datetime.now(timezone.utc).isoformat(),json.dumps(clean),max(0,min(int(latency_ms),86400000)),category))
            conn.execute('DELETE FROM oracle_local_ai_events WHERE scope=? AND id NOT IN (SELECT id FROM oracle_local_ai_events WHERE scope=? ORDER BY id DESC LIMIT ?)', (scope,scope,MAX_EVENTS))
    finally:
        conn.close()


def recent(scope, limit=10):
    scope = _scope(scope)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_EVENTS:
        raise ValueError('invalid limit')
    conn = get_conn()
    try:
        with conn:
            _schema(conn)
        return [dict(row) for row in conn.execute('SELECT workload,phase,model,created_at,counts_json,latency_ms,error_category FROM oracle_local_ai_events WHERE scope=? ORDER BY id DESC LIMIT ?', (scope,limit))]
    finally:
        conn.close()


def best_effort(*args, **kwargs):
    try:
        record(*args, **kwargs)
    except Exception:
        pass  # Telemetry must not change execution results.
