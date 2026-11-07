"""
database.py — وحدة قاعدة البيانات المحلية (SQLite) للذاكرة والمنح المكتشفة
Local SQLite module managing two core tables:

  - whatsapp_chats         : ذاكرة محادثات الواتساب (مرسِل، رسالة واردة، رد ذكي، توقيت)
  - discovered_scholarships: المنح المكتشفة تلقائياً (اسم، رابط، شروط، تاريخ الاكتشاف)

تستخدم نفس ملف SQLite الخاص بـ db.py (قاعدة بيانات واحدة متماسكة)، ومساره عبر
متغيّر البيئة ORACLE_DB_PATH.
"""

from datetime import datetime
import os

# نعيد استخدام نفس الاتصال/المسار/الإعدادات من db.py لضمان قاعدة بيانات واحدة
from db import get_conn, init_db, DB_PATH, get_setting, set_setting  # noqa: F401


# --------------------------------------------------------------------------
# التهيئة
# --------------------------------------------------------------------------
def init_database():
    """ينشئ الجدولين إن لم يكونا موجودين. آمن للاستدعاء أكثر من مرة."""
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS whatsapp_chats (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            sender           TEXT,
            incoming_message TEXT,
            smart_reply      TEXT,
            timestamp        TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_chats_sender ON whatsapp_chats(sender);

        CREATE TABLE IF NOT EXISTS discovered_scholarships (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT,
            url           TEXT UNIQUE,
            requirements  TEXT,
            source        TEXT,
            discovered_at TEXT
        );

        CREATE TABLE IF NOT EXISTS schedules (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day         TEXT UNIQUE,
            created_at  TEXT,
            plan_json   TEXT,
            goals_json  TEXT,
            energy_json TEXT
        );

        CREATE TABLE IF NOT EXISTS generated_content (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT,
            content_type TEXT,
            topic        TEXT,
            body         TEXT
        );

        CREATE TABLE IF NOT EXISTS feature_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ts           TEXT,
            feature_id   INTEGER,
            feature_name TEXT,
            status       TEXT,
            detail       TEXT
        );

        -- الوحدة الخارقة: جداول الميزات المتقدمة
        CREATE TABLE IF NOT EXISTS promises (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            person    TEXT,
            promise   TEXT,
            due       TEXT,
            status    TEXT DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS bills (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT,
            amount    REAL,
            cycle     TEXT,
            next_due  TEXT,
            note      TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS financial_tracker (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT,
            type      TEXT,          -- income | expense | subscription
            category  TEXT,
            amount    REAL,
            currency  TEXT DEFAULT 'EGP',
            note      TEXT
        );

        CREATE TABLE IF NOT EXISTS user_wellbeing (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT,
            mood      INTEGER,
            energy    INTEGER,
            stress    INTEGER,
            note      TEXT
        );

        CREATE TABLE IF NOT EXISTS password_vault (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            label      TEXT,
            username   TEXT,
            secret_enc TEXT,
            created_at TEXT
        );

        -- ماكينة الدخل التلقائي (income_hunter)
        CREATE TABLE IF NOT EXISTS freelance_proposals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            platform  TEXT,
            project   TEXT,
            skills    TEXT,
            price     REAL,
            currency  TEXT DEFAULT 'USD',
            proposal  TEXT,
            status    TEXT DEFAULT 'drafted'   -- lead | drafted | sent | won | lost
        );

        CREATE TABLE IF NOT EXISTS digital_sales (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            product   TEXT,
            price     REAL,
            currency  TEXT DEFAULT 'USD',
            buyer     TEXT,
            link      TEXT,
            status    TEXT DEFAULT 'product'   -- product | sold
        );

        CREATE TABLE IF NOT EXISTS affiliate_clicks (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            ts             TEXT,
            product        TEXT,
            link           TEXT,
            clicks         INTEGER DEFAULT 0,
            est_commission REAL DEFAULT 0,
            currency       TEXT DEFAULT 'USD'
        );

        CREATE TABLE IF NOT EXISTS ad_revenue (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            date      TEXT,
            source    TEXT,
            amount    REAL,
            currency  TEXT DEFAULT 'USD',
            views     INTEGER DEFAULT 0
        );

        -- إمبراطورية الدخل (wealth_empire)
        CREATE TABLE IF NOT EXISTS revenue_streams (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            stream    TEXT,          -- freelance | digital | affiliate | seo | arbitrage | agency
            amount    REAL,
            currency  TEXT DEFAULT 'USD',
            note      TEXT
        );

        CREATE TABLE IF NOT EXISTS affiliate_logs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            ts          TEXT,
            product     TEXT,
            link        TEXT,
            clicks      INTEGER DEFAULT 0,
            conversions INTEGER DEFAULT 0,
            revenue     REAL DEFAULT 0,
            currency    TEXT DEFAULT 'USD'
        );

        CREATE TABLE IF NOT EXISTS seo_metrics (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT,
            keyword    TEXT,
            cpm        REAL,
            difficulty TEXT,
            url        TEXT,
            status     TEXT DEFAULT 'idea'   -- idea | drafted | published
        );

        CREATE TABLE IF NOT EXISTS freelance_contracts (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ts        TEXT,
            client    TEXT,
            project   TEXT,
            amount    REAL,
            currency  TEXT DEFAULT 'USD',
            status    TEXT DEFAULT 'draft',  -- draft | sent | signed | paid
            body      TEXT
        );

        -- محراب الانضباط (discipline_oracle)
        CREATE TABLE IF NOT EXISTS future_milestones (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            level      TEXT,          -- decade | year | month | day
            horizon    TEXT,          -- وصف الأفق الزمني
            title      TEXT,
            detail     TEXT,
            due        TEXT,
            status     TEXT DEFAULT 'open'
        );

        CREATE TABLE IF NOT EXISTS youtube_automation_logs (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            ts      TEXT,
            action  TEXT,             -- script | comment_draft | trend
            video   TEXT,
            detail  TEXT
        );

        CREATE TABLE IF NOT EXISTS discipline_matrix (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT,
            command TEXT,
            status  TEXT DEFAULT 'issued',  -- issued | done | skipped
            note    TEXT
        );

        CREATE TABLE IF NOT EXISTS memories (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            content            TEXT NOT NULL,
            normalized_content TEXT NOT NULL,
            memory_type        TEXT NOT NULL,
            scope              TEXT NOT NULL,
            source             TEXT NOT NULL,
            created_at         TEXT NOT NULL,
            UNIQUE(normalized_content, memory_type, scope)
        );
        CREATE INDEX IF NOT EXISTS idx_memories_scope_created
            ON memories(scope, created_at DESC, id DESC);

        -- Episodic memory: explicitly recorded events with source and time provenance.
        CREATE TABLE IF NOT EXISTS memory_events (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            scope              TEXT NOT NULL,
            event_type         TEXT NOT NULL,
            summary            TEXT NOT NULL,
            normalized_summary TEXT NOT NULL,
            details_json       TEXT NOT NULL DEFAULT '{}',
            source             TEXT NOT NULL,
            happened_at        TEXT NOT NULL,
            recorded_at        TEXT NOT NULL,
            UNIQUE(scope, event_type, normalized_summary, happened_at)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_events_scope_time
            ON memory_events(scope, happened_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_memory_events_scope_type_time
            ON memory_events(scope, event_type, happened_at DESC);

        -- Procedural memory: candidate workflows become retrievable only after validation.
        CREATE TABLE IF NOT EXISTS memory_procedures (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scope           TEXT NOT NULL,
            name            TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            description     TEXT NOT NULL,
            steps_json      TEXT NOT NULL,
            source          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'candidate',
            success_count   INTEGER NOT NULL DEFAULT 0,
            failure_count   INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE(scope, normalized_name),
            CHECK(status IN ('candidate', 'validated', 'retired')),
            CHECK(success_count >= 0),
            CHECK(failure_count >= 0)
        );
        CREATE INDEX IF NOT EXISTS idx_memory_procedures_scope_status
            ON memory_procedures(scope, status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS knowledge_entities (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            scope           TEXT NOT NULL,
            name            TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            entity_type     TEXT NOT NULL,
            attributes_json TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE(scope, normalized_name),
            UNIQUE(id, scope)
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_entities_scope_name
            ON knowledge_entities(scope, normalized_name);

        CREATE TABLE IF NOT EXISTS knowledge_relations (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            scope            TEXT NOT NULL,
            source_entity_id INTEGER NOT NULL,
            target_entity_id INTEGER NOT NULL,
            relation_type    TEXT NOT NULL,
            evidence         TEXT NOT NULL DEFAULT '',
            created_at       TEXT NOT NULL,
            UNIQUE(scope, source_entity_id, target_entity_id, relation_type)
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_relations_source
            ON knowledge_relations(scope, source_entity_id, relation_type);
        CREATE INDEX IF NOT EXISTS idx_knowledge_relations_target
            ON knowledge_relations(scope, target_entity_id, relation_type);

        CREATE TABLE IF NOT EXISTS oracle_workflow_runs (
            workflow_id  TEXT PRIMARY KEY,
            scope        TEXT NOT NULL,
            task_digest  TEXT NOT NULL,
            status       TEXT NOT NULL,
            max_steps    INTEGER NOT NULL,
            created_at   TEXT NOT NULL,
            updated_at   TEXT NOT NULL,
            finished_at  TEXT,
            error_code   TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_oracle_workflow_runs_scope_created
            ON oracle_workflow_runs(scope, created_at DESC);

        CREATE TABLE IF NOT EXISTS oracle_workflow_steps (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id    TEXT NOT NULL,
            scope          TEXT NOT NULL,
            step_index     INTEGER NOT NULL,
            tool_id        TEXT NOT NULL,
            status         TEXT NOT NULL,
            input_digest   TEXT NOT NULL,
            output_digest  TEXT NOT NULL DEFAULT '',
            input_length   INTEGER NOT NULL DEFAULT 0,
            output_length  INTEGER NOT NULL DEFAULT 0,
            duration_ms    INTEGER,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL,
            UNIQUE(workflow_id, step_index)
        );
        CREATE INDEX IF NOT EXISTS idx_oracle_workflow_steps_scope_run
            ON oracle_workflow_steps(scope, workflow_id, step_index);

        CREATE TABLE IF NOT EXISTS oracle_execution_approvals (
            approval_id TEXT PRIMARY KEY, scope TEXT NOT NULL, tool_id TEXT NOT NULL,
            action_digest TEXT NOT NULL, preview_json TEXT NOT NULL, status TEXT NOT NULL,
            created_at REAL NOT NULL, expires_at REAL NOT NULL, decided_at REAL,
            checkpoint_id TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_oracle_approvals_scope_status
            ON oracle_execution_approvals(scope, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS oracle_workflow_checkpoints (
            checkpoint_id TEXT PRIMARY KEY, scope TEXT NOT NULL, ciphertext TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL, expires_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_oracle_checkpoints_scope_expiry
            ON oracle_workflow_checkpoints(scope, expires_at);

        CREATE TABLE IF NOT EXISTS oracle_model_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT NOT NULL, provider TEXT NOT NULL,
            model TEXT NOT NULL, route_reason TEXT NOT NULL, latency_ms INTEGER NOT NULL,
            outcome TEXT NOT NULL, output_chars INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_oracle_model_events_scope_id
            ON oracle_model_events(scope, id DESC);
        """
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# whatsapp_chats — ذاكرة المحادثات
# --------------------------------------------------------------------------
def save_chat(sender: str, incoming_message: str, smart_reply: str) -> int:
    """يحفظ تبادلاً واحداً (رسالة + رد) لبناء ذاكرة المحادثة."""
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO whatsapp_chats(sender, incoming_message, smart_reply, timestamp) "
        "VALUES(?,?,?,?)",
        (sender, incoming_message, smart_reply,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def get_chat_history(sender: str, limit: int = 6) -> list:
    """يُرجع آخر تبادلات هذا المرسِل مرتّبة زمنياً (الأقدم أولاً) للاستخدام كذاكرة."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM whatsapp_chats WHERE sender = ? ORDER BY id DESC LIMIT ?",
        (sender, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def list_chats(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM whatsapp_chats ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# discovered_scholarships — المنح المكتشفة
# --------------------------------------------------------------------------
def save_scholarship(name: str, url: str, requirements: str = "",
                     source: str = "") -> int:
    """يحفظ منحة مكتشفة (تجاهل المكرر حسب الرابط). يُعيد 1 إذا أُضيفت، 0 إن كانت موجودة."""
    url = (url or "").strip()
    if not url:
        return 0
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO discovered_scholarships"
        "(name, url, requirements, source, discovered_at) VALUES(?,?,?,?,?)",
        (name or url, url, requirements or "", source or "",
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def save_scholarships(items: list) -> int:
    """يحفظ قائمة منح. كل عنصر: {name, url, requirements?, source?}. يُعيد عدد المُضاف."""
    added = 0
    for it in items or []:
        added += save_scholarship(
            it.get("name", ""), it.get("url", ""),
            it.get("requirements", ""), it.get("source", ""),
        )
    return added


def list_discovered_scholarships(limit: int = 200) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, url, requirements, source, discovered_at "
        "FROM discovered_scholarships ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def discovered_count() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM discovered_scholarships").fetchone()["c"]
    conn.close()
    return n


def clear_discovered():
    conn = get_conn()
    conn.execute("DELETE FROM discovered_scholarships")
    conn.commit()
    conn.close()


import json as _json


# --------------------------------------------------------------------------
# schedules — جداول الحركة اليومية (المخطط الصارم)
# --------------------------------------------------------------------------
def save_schedule(day: str, plan: list, goals: list, energy: dict) -> None:
    init_database()
    conn = get_conn()
    conn.execute(
        "INSERT INTO schedules(day, created_at, plan_json, goals_json, energy_json) "
        "VALUES(?,?,?,?,?) ON CONFLICT(day) DO UPDATE SET "
        "created_at=excluded.created_at, plan_json=excluded.plan_json, "
        "goals_json=excluded.goals_json, energy_json=excluded.energy_json",
        (day, datetime.now().isoformat(timespec="seconds"),
         _json.dumps(plan, ensure_ascii=False),
         _json.dumps(goals, ensure_ascii=False),
         _json.dumps(energy, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_schedule(day: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM schedules WHERE day = ?", (day,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "day": row["day"], "created_at": row["created_at"],
        "plan": _json.loads(row["plan_json"] or "[]"),
        "goals": _json.loads(row["goals_json"] or "[]"),
        "energy": _json.loads(row["energy_json"] or "{}"),
    }


# --------------------------------------------------------------------------
# generated_content — المحتوى المُولَّد
# --------------------------------------------------------------------------
def save_content(content_type: str, topic: str, body: str) -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO generated_content(created_at, content_type, topic, body) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), content_type, topic, body),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid


def list_content(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM generated_content ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# feature_log — سجل تشغيل الـ50 ميزة
# --------------------------------------------------------------------------
def log_feature(feature_id: int, feature_name: str, status: str, detail: str = "") -> None:
    init_database()
    conn = get_conn()
    conn.execute(
        "INSERT INTO feature_log(ts, feature_id, feature_name, status, detail) VALUES(?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), feature_id, feature_name,
         status, (detail or "")[:500]),
    )
    conn.commit()
    conn.close()


def list_feature_log(limit: int = 30) -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT ts, feature_id, feature_name, status, detail FROM feature_log "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# promises — حافظ الوعود
# --------------------------------------------------------------------------
def add_promise(person: str, promise: str, due: str = "") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO promises(ts, person, promise, due, status) VALUES(?,?,?,?, 'open')",
        (datetime.now().isoformat(timespec="seconds"), person, promise, due),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_promises(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM promises ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_promise_status(pid: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE promises SET status = ? WHERE id = ?", (status, pid))
    conn.commit(); conn.close()


# --------------------------------------------------------------------------
# bills + financial_tracker — المال
# --------------------------------------------------------------------------
def add_bill(name: str, amount: float, cycle: str, next_due: str, note: str = "") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO bills(name, amount, cycle, next_due, note, created_at) VALUES(?,?,?,?,?,?)",
        (name, float(amount or 0), cycle, next_due, note,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_bills(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM bills ORDER BY next_due ASC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_finance(date: str, type_: str, category: str, amount: float,
                currency: str = "EGP", note: str = "") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO financial_tracker(date, type, category, amount, currency, note) "
        "VALUES(?,?,?,?,?,?)",
        (date or datetime.now().strftime("%Y-%m-%d"), type_, category,
         float(amount or 0), currency, note),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_finance(limit: int = 200) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM financial_tracker ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def finance_summary() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT type, SUM(amount) AS total FROM financial_tracker "
                        "GROUP BY type").fetchall()
    conn.close()
    out = {"income": 0.0, "expense": 0.0, "subscription": 0.0}
    for r in rows:
        out[r["type"]] = round(r["total"] or 0, 2)
    out["balance"] = round(out["income"] - out["expense"] - out["subscription"], 2)
    return out


# --------------------------------------------------------------------------
# user_wellbeing — الطاقة والمود والتوتر
# --------------------------------------------------------------------------
def add_wellbeing(mood: int, energy: int, stress: int, note: str = "") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO user_wellbeing(date, mood, energy, stress, note) VALUES(?,?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), int(mood), int(energy),
         int(stress), note),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_wellbeing(limit: int = 60) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM user_wellbeing ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# password_vault — خزنة كلمات السر
# --------------------------------------------------------------------------
class VaultConfigurationError(RuntimeError):
    """Raised when the external encryption key is missing or invalid."""


class VaultMigrationError(RuntimeError):
    """Raised when an existing vault cannot be safely re-encrypted."""


def _fernet():
    """Build Fernet only from an environment secret, never from the database."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise VaultConfigurationError(
            "cryptography is required to use the password vault"
        ) from exc

    key = os.environ.get("ORACLE_VAULT_KEY", "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise VaultConfigurationError(
            "ORACLE_VAULT_KEY must be a valid Fernet key"
        ) from exc


def _enc(secret: str) -> str:
    fernet = _fernet()
    if fernet is None:
        raise VaultConfigurationError(
            "Set ORACLE_VAULT_KEY before saving passwords; plaintext/Base64 fallback is disabled"
        )
    if not isinstance(secret, str):
        raise TypeError("vault secret must be text")
    return "f:" + fernet.encrypt(secret.encode("utf-8")).decode("ascii")


def _dec(blob: str) -> str:
    if not isinstance(blob, str) or not blob.startswith("f:"):
        return "🔒(تحتاج ترحيلاً إلى مفتاح الخزنة الخارجي)"
    fernet = _fernet()
    if fernet is None:
        return "🔒(اضبط ORACLE_VAULT_KEY لعرض الأسرار)"
    try:
        return fernet.decrypt(blob[2:].encode("ascii")).decode("utf-8")
    except Exception:
        return "🔒(مفتاح الخزنة غير مطابق أو البيانات تالفة)"


def migrate_legacy_vault_key() -> int:
    """Re-encrypt legacy DB-key/Base64 rows with ORACLE_VAULT_KEY, then remove the DB key."""
    fernet = _fernet()
    if fernet is None:
        return 0

    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError as exc:  # pragma: no cover - guarded by _fernet
        raise VaultConfigurationError("cryptography is required") from exc

    init_db()
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        key_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'vault_key'"
        ).fetchone()
        legacy_fernet = None
        if key_row is not None:
            try:
                legacy_fernet = Fernet(key_row["value"].encode("ascii"))
            except Exception as exc:
                raise VaultMigrationError(
                    "The legacy vault key is invalid; no records were changed"
                ) from exc

        rows = conn.execute(
            "SELECT id, secret_enc FROM password_vault ORDER BY id"
        ).fetchall()
        migrated = 0
        for row in rows:
            blob = row["secret_enc"] or ""
            try:
                if blob.startswith("f:"):
                    token = blob[2:].encode("ascii")
                    try:
                        plaintext = fernet.decrypt(token)
                    except InvalidToken:
                        if legacy_fernet is None:
                            raise VaultMigrationError(
                                f"Vault record {row['id']} needs its legacy key"
                            )
                        plaintext = legacy_fernet.decrypt(token)
                elif blob.startswith("b:"):
                    import base64
                    plaintext = base64.b64decode(blob[2:].encode("ascii"), validate=True)
                else:
                    raise VaultMigrationError(
                        f"Vault record {row['id']} has an unsupported legacy format"
                    )
                encrypted = "f:" + fernet.encrypt(plaintext).decode("ascii")
            except (InvalidToken, ValueError, UnicodeEncodeError) as exc:
                raise VaultMigrationError(
                    f"Vault record {row['id']} could not be migrated; no records were changed"
                ) from exc

            conn.execute(
                "UPDATE password_vault SET secret_enc = ? WHERE id = ?",
                (encrypted, row["id"]),
            )
            migrated += 1

        conn.execute("DELETE FROM settings WHERE key = 'vault_key'")
        conn.commit()
        return migrated
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def add_vault_entry(label: str, username: str, secret: str) -> int:
    init_database()
    encrypted = _enc(secret)
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO password_vault(label, username, secret_enc, created_at) VALUES(?,?,?,?)",
            (label, username, encrypted, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_vault(reveal: bool = False) -> list:
    if reveal:
        migrate_legacy_vault_key()
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM password_vault ORDER BY id DESC").fetchall()
        out = []
        for row in rows:
            item = dict(row)
            item["secret"] = _dec(item["secret_enc"]) if reveal else "••••••••"
            item.pop("secret_enc", None)
            out.append(item)
        return out
    finally:
        conn.close()


# --------------------------------------------------------------------------
# ماكينة الدخل — freelance_proposals / digital_sales / affiliate / ad_revenue
# --------------------------------------------------------------------------
def add_proposal(platform, project, skills, price, currency, proposal, status="drafted") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO freelance_proposals(ts, platform, project, skills, price, currency, "
        "proposal, status) VALUES(?,?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), platform, project,
         skills, float(price or 0), currency, proposal, status),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_proposals(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM freelance_proposals ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_proposal_status(pid: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE freelance_proposals SET status = ? WHERE id = ?", (status, pid))
    conn.commit(); conn.close()


def add_digital_product(product, price, currency="USD", link="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO digital_sales(ts, product, price, currency, buyer, link, status) "
        "VALUES(?,?,?,?,?,?, 'product')",
        (datetime.now().isoformat(timespec="seconds"), product, float(price or 0),
         currency, "", link),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def record_sale(product, price, currency="USD", buyer="", link="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO digital_sales(ts, product, price, currency, buyer, link, status) "
        "VALUES(?,?,?,?,?,?, 'sold')",
        (datetime.now().isoformat(timespec="seconds"), product, float(price or 0),
         currency, buyer, link),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_digital_sales(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM digital_sales ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_affiliate(product, link, clicks=0, est_commission=0.0, currency="USD") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO affiliate_clicks(ts, product, link, clicks, est_commission, currency) "
        "VALUES(?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), product, link,
         int(clicks or 0), float(est_commission or 0), currency),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_affiliate(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM affiliate_clicks ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_ad_revenue(date, source, amount, currency="USD", views=0) -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO ad_revenue(date, source, amount, currency, views) VALUES(?,?,?,?,?)",
        (date or datetime.now().strftime("%Y-%m-%d"), source,
         float(amount or 0), currency, int(views or 0)),
    )
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_ad_revenue(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM ad_revenue ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def revenue_summary() -> dict:
    """يجمّع مؤشرات الأرباح من كل المصادر. العملات مفصولة USD/EGP."""
    conn = get_conn()
    q = conn.execute
    proposals_total = q("SELECT COUNT(*) c FROM freelance_proposals").fetchone()["c"]
    proposals_sent = q("SELECT COUNT(*) c FROM freelance_proposals "
                       "WHERE status IN ('sent','won')").fetchone()["c"]
    proposals_won = q("SELECT COUNT(*) c FROM freelance_proposals "
                      "WHERE status='won'").fetchone()["c"]
    products = q("SELECT COUNT(*) c FROM digital_sales WHERE status='product'").fetchone()["c"]
    sold = q("SELECT COUNT(*) c FROM digital_sales WHERE status='sold'").fetchone()["c"]

    def _sum(query):
        return {r["currency"] or "USD": round(r["t"] or 0, 2) for r in q(query).fetchall()}

    sales_rev = _sum("SELECT currency, SUM(price) t FROM digital_sales "
                     "WHERE status='sold' GROUP BY currency")
    aff_rev = _sum("SELECT currency, SUM(est_commission) t FROM affiliate_clicks GROUP BY currency")
    ad_rev = _sum("SELECT currency, SUM(amount) t FROM ad_revenue GROUP BY currency")
    clicks = q("SELECT COALESCE(SUM(clicks),0) c FROM affiliate_clicks").fetchone()["c"]
    conn.close()

    def merge(*dicts):
        out = {"USD": 0.0, "EGP": 0.0}
        for d in dicts:
            for k, v in d.items():
                out[k] = round(out.get(k, 0) + v, 2)
        return out

    total = merge(sales_rev, aff_rev, ad_rev)
    leads_funnel = proposals_total + clicks
    conversion = round((sold / leads_funnel * 100), 1) if leads_funnel else 0.0
    return {
        "proposals_total": proposals_total, "proposals_sent": proposals_sent,
        "proposals_won": proposals_won, "products": products, "sold": sold,
        "affiliate_clicks": clicks,
        "sales_revenue": sales_rev, "affiliate_revenue": aff_rev, "ad_revenue": ad_rev,
        "total_revenue": total, "conversion_rate": conversion,
    }


# --------------------------------------------------------------------------
# إمبراطورية الدخل — revenue_streams / affiliate_logs / seo_metrics / freelance_contracts
# --------------------------------------------------------------------------
def add_revenue_stream(stream, amount, currency="USD", note="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO revenue_streams(ts, stream, amount, currency, note) VALUES(?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), stream, float(amount or 0),
         currency, note))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def revenue_by_stream() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT stream, currency, SUM(amount) t FROM revenue_streams "
                        "GROUP BY stream, currency").fetchall()
    conn.close()
    out = {}
    for r in rows:
        out.setdefault(r["stream"], {})[r["currency"] or "USD"] = round(r["t"] or 0, 2)
    return out


def add_affiliate_log(product, link, clicks=0, conversions=0, revenue=0.0, currency="USD") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO affiliate_logs(ts, product, link, clicks, conversions, revenue, currency) "
        "VALUES(?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), product, link, int(clicks or 0),
         int(conversions or 0), float(revenue or 0), currency))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_affiliate_logs(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM affiliate_logs ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_seo_metric(keyword, cpm, difficulty="", url="", status="idea") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO seo_metrics(ts, keyword, cpm, difficulty, url, status) VALUES(?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), keyword, float(cpm or 0),
         difficulty, url, status))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_seo_metrics(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM seo_metrics ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_contract(client, project, amount, currency="USD", status="draft", body="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO freelance_contracts(ts, client, project, amount, currency, status, body) "
        "VALUES(?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), client, project,
         float(amount or 0), currency, status, body))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_contracts(limit: int = 100) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM freelance_contracts ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def roi_dashboard() -> dict:
    """عائد كل قطاع مالي (من revenue_streams) لتوجيه التركيز للأعلى ربحاً."""
    by = revenue_by_stream()
    totals = {k: sum(v.values()) for k, v in by.items()}
    best = max(totals, key=totals.get) if totals else None
    return {"by_stream": by, "totals_mixed": totals, "best_stream": best}


# --------------------------------------------------------------------------
# محراب الانضباط — future_milestones / youtube_automation_logs / discipline_matrix
# --------------------------------------------------------------------------
def add_milestone(level, horizon, title, detail="", due="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO future_milestones(created_at, level, horizon, title, detail, due, status) "
        "VALUES(?,?,?,?,?,?, 'open')",
        (datetime.now().isoformat(timespec="seconds"), level, horizon, title, detail, due))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_milestones(level: str = None, limit: int = 200) -> list:
    conn = get_conn()
    if level:
        rows = conn.execute("SELECT * FROM future_milestones WHERE level = ? ORDER BY id DESC "
                            "LIMIT ?", (level, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM future_milestones ORDER BY id DESC LIMIT ?",
                            (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_milestones():
    conn = get_conn()
    conn.execute("DELETE FROM future_milestones")
    conn.commit(); conn.close()


def add_youtube_log(action, video, detail="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO youtube_automation_logs(ts, action, video, detail) VALUES(?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), action, video, (detail or "")[:1000]))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_youtube_logs(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM youtube_automation_logs ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_discipline(command, status="issued", note="") -> int:
    init_database()
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO discipline_matrix(date, command, status, note) VALUES(?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M"), command, status, note))
    conn.commit(); rid = cur.lastrowid; conn.close()
    return rid


def list_discipline(limit: int = 50) -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM discipline_matrix ORDER BY id DESC LIMIT ?",
                        (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_discipline_status(did: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE discipline_matrix SET status = ? WHERE id = ?", (status, did))
    conn.commit(); conn.close()


# --------------------------------------------------------------------------
# 🛑 Panic Button — التدمير الذاتي للسجلات الحساسة
# --------------------------------------------------------------------------
SENSITIVE_TABLES = [
    "whatsapp_chats", "wa_messages", "contacts", "entries", "generated_content",
    "financial_tracker", "bills", "user_wellbeing", "promises", "password_vault",
    "feature_log", "memories", "knowledge_relations", "knowledge_entities",
    "oracle_workflow_steps", "oracle_workflow_runs", "oracle_execution_approvals",
    "oracle_workflow_checkpoints", "oracle_model_events", "wa_processed_messages",
]


def panic_wipe(tables: list = None) -> dict:
    """Delete only explicitly allowlisted sensitive tables in one transaction."""
    init_database()
    allowed = set(SENSITIVE_TABLES)
    if tables is None:
        targets = list(SENSITIVE_TABLES)
    else:
        if not isinstance(tables, (list, tuple, set)):
            raise TypeError("tables must be a list, tuple, set, or None")
        requested = list(tables)
        invalid = [
            item for item in requested
            if not isinstance(item, str) or item not in allowed
        ]
        if invalid:
            raise ValueError("panic wipe accepts allowlisted table names only")
        targets = list(dict.fromkeys(requested))

    if not targets:
        return {}

    conn = get_conn()
    wiped = {}
    try:
        conn.execute("BEGIN IMMEDIATE")
        for table_name in targets:
            count = conn.execute(
                f"SELECT COUNT(*) AS c FROM {table_name}"
            ).fetchone()["c"]
            conn.execute(f"DELETE FROM {table_name}")
            wiped[table_name] = count
        conn.commit()
        return wiped
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    init_database()
    print("✅ database.py initialized at:", DB_PATH)
    print("chats:", len(list_chats()), "| scholarships:", discovered_count())
