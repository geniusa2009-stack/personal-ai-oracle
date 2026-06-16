"""
db.py — طبقة قاعدة البيانات المشتركة (SQLite)
Shared SQLite layer used by both the Streamlit app and the background worker.

مسار قاعدة البيانات قابل للضبط عبر متغيّر بيئة ORACLE_DB_PATH (مهم للسحابة).
The DB path is configurable via the ORACLE_DB_PATH environment variable (key for cloud disks).
"""

import os
import json
import sqlite3
from datetime import datetime

# على السحابة: اضبط ORACLE_DB_PATH=/data/oracle.db (قرص دائم)
# محلياً: يُحفظ داخل مجلد المستخدم
DB_PATH = os.environ.get("ORACLE_DB_PATH") or os.path.join(
    os.path.expanduser("~"), ".personal_ai_oracle", "oracle.db"
)


def get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")  # يسمح بقراءة/كتابة متزامنة بين الـ app والـ worker
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT,
            text        TEXT,
            keywords    TEXT
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            found_at  TEXT,
            category  TEXT,
            keyword   TEXT,
            title     TEXT,
            url       TEXT UNIQUE,
            snippet   TEXT,
            source    TEXT,
            score     INTEGER DEFAULT 50,
            summary   TEXT,
            seen      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_id         TEXT UNIQUE,
            name          TEXT,
            relationship  TEXT DEFAULT 'friend',
            tone          TEXT DEFAULT 'casual',
            notes         TEXT DEFAULT '',
            created_at    TEXT
        );

        CREATE TABLE IF NOT EXISTS wa_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ts         TEXT,
            wa_id      TEXT,
            direction  TEXT,          -- in | out | draft
            body       TEXT,
            status     TEXT           -- received | draft | sent | failed
        );
        """
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# جهات اتصال واتساب (contacts)
# --------------------------------------------------------------------------
def upsert_contact(wa_id: str, name: str = None) -> dict:
    conn = get_conn()
    row = conn.execute("SELECT * FROM contacts WHERE wa_id = ?", (wa_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO contacts(wa_id, name, created_at) VALUES(?,?,?)",
            (wa_id, name or wa_id, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE wa_id = ?", (wa_id,)).fetchone()
    elif name and (not row["name"] or row["name"] == row["wa_id"]):
        conn.execute("UPDATE contacts SET name = ? WHERE wa_id = ?", (name, wa_id))
        conn.commit()
        row = conn.execute("SELECT * FROM contacts WHERE wa_id = ?", (wa_id,)).fetchone()
    conn.close()
    return dict(row)


def get_contact(wa_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM contacts WHERE wa_id = ?", (wa_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_contact(wa_id: str, **fields):
    allowed = {"name", "relationship", "tone", "notes"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    conn = get_conn()
    cols = ", ".join(f"{k} = ?" for k in sets)
    conn.execute(f"UPDATE contacts SET {cols} WHERE wa_id = ?",
                 (*sets.values(), wa_id))
    conn.commit()
    conn.close()


def list_contacts() -> list:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM contacts ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# رسائل ومسودّات واتساب (wa_messages)
# --------------------------------------------------------------------------
def log_wa_message(wa_id: str, direction: str, body: str, status: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO wa_messages(ts, wa_id, direction, body, status) VALUES(?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), wa_id, direction, body, status),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return mid


def list_wa_messages(wa_id: str = None, status: str = None, limit: int = 100) -> list:
    conn = get_conn()
    clauses, params = [], []
    if wa_id:
        clauses.append("wa_id = ?"); params.append(wa_id)
    if status:
        clauses.append("status = ?"); params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM wa_messages {where} ORDER BY id DESC LIMIT ?", params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_message_status(message_id: int, status: str):
    conn = get_conn()
    conn.execute("UPDATE wa_messages SET status = ? WHERE id = ?", (status, message_id))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# الإعدادات (settings)
# --------------------------------------------------------------------------
def get_setting(key: str, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------
# اليوميات (entries)
# --------------------------------------------------------------------------
def save_entry(text: str, keywords: list):
    conn = get_conn()
    conn.execute(
        "INSERT INTO entries(created_at, text, keywords) VALUES(?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), text,
         json.dumps(keywords, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def recent_entry_keywords(limit_entries: int = 15) -> list:
    """يجمع الكلمات المفتاحية من آخر اليوميات لاستخدامها في البحث التلقائي."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT keywords FROM entries ORDER BY id DESC LIMIT ?", (limit_entries,)
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            out.extend(json.loads(r["keywords"] or "[]"))
        except Exception:
            continue
    # إزالة التكرار مع الحفاظ على الترتيب
    seen, uniq = set(), []
    for k in out:
        k = (k or "").strip()
        if k and k.lower() not in seen:
            seen.add(k.lower())
            uniq.append(k)
    return uniq


# --------------------------------------------------------------------------
# الفرص (opportunities)
# --------------------------------------------------------------------------
def add_opportunities(items: list) -> int:
    """يدرج الفرص الجديدة فقط (تجاهل المكرر حسب الرابط). يُعيد عدد المُضاف."""
    if not items:
        return 0
    conn = get_conn()
    added = 0
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        cur = conn.execute(
            """INSERT OR IGNORE INTO opportunities
               (found_at, category, keyword, title, url, snippet, source, score, summary)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                it.get("found_at") or datetime.now().isoformat(timespec="seconds"),
                it.get("category", ""), it.get("keyword", ""),
                it.get("title", ""), url, it.get("snippet", ""),
                it.get("source", ""), int(it.get("score", 50)),
                it.get("summary", ""),
            ),
        )
        added += cur.rowcount
    conn.commit()
    conn.close()
    return added


def list_opportunities(category: str = None, limit: int = 100) -> list:
    conn = get_conn()
    if category and category != "all":
        rows = conn.execute(
            "SELECT * FROM opportunities WHERE category = ? "
            "ORDER BY score DESC, id DESC LIMIT ?", (category, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM opportunities ORDER BY score DESC, id DESC LIMIT ?",
            (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def opportunities_count() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM opportunities").fetchone()["c"]
    conn.close()
    return n


def clear_opportunities():
    conn = get_conn()
    conn.execute("DELETE FROM opportunities")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("DB initialized at:", DB_PATH)
