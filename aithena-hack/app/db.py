"""
SQLite database — one file, no server, no migrations.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.db")


def get_conn():
    # timeout=30.0: how long SQLite will wait for a write lock to free up
    # before giving up with "database is locked", instead of the 5-second
    # default. This is a safety margin, not the real fix — the real fix is
    # in main.py, keeping write transactions short. But with several
    # documents finishing around the same moment, a little extra patience
    # here means a brief queue instead of an error.
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            parties TEXT,
            contract_type TEXT,
            start_date TEXT,
            end_date TEXT,
            renewal_type TEXT,
            notice_period_days INTEGER,
            notice_deadline TEXT,
            governing_law TEXT,
            is_scanned INTEGER DEFAULT 0,
            clauses_total INTEGER,
            clauses_covered INTEGER,
            supersedes_id INTEGER REFERENCES contracts(id),
            raw_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fields (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL REFERENCES contracts(id),
            field_name TEXT NOT NULL,
            value TEXT,
            value_alt TEXT,
            confidence TEXT NOT NULL DEFAULT 'UNGROUNDED',
            verbatim_quote TEXT,
            quote_match_score REAL,
            page INTEGER,
            bbox TEXT,
            extractor_a_raw TEXT,
            extractor_b_raw TEXT,
            adversary_note TEXT
        );

        CREATE TABLE IF NOT EXISTS conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_a_id INTEGER REFERENCES contracts(id),
            contract_b_id INTEGER REFERENCES contracts(id),
            kind TEXT NOT NULL,
            description TEXT,
            severity TEXT DEFAULT 'medium'
        );

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL REFERENCES contracts(id),
            page_number INTEGER NOT NULL,
            text_content TEXT,
            has_text INTEGER DEFAULT 1,
            image_path TEXT
        );

        CREATE TABLE IF NOT EXISTS gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_contract_id INTEGER REFERENCES contracts(id),
            source_filename TEXT,
            kind TEXT NOT NULL,
            reference_text TEXT,
            page INTEGER,
            resolution TEXT NOT NULL,
            candidates TEXT,
            language_note TEXT
        );

        CREATE TABLE IF NOT EXISTS risk_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER REFERENCES contracts(id),
            field_name TEXT NOT NULL,
            assertion TEXT NOT NULL,
            severity TEXT NOT NULL,
            basis TEXT,
            evidence TEXT,
            benchmark_note TEXT,
            requires_lawyer INTEGER DEFAULT 0
        );
    """)
    # Party-role columns on contracts — added via ALTER so existing databases
    # upgrade in place. Wrapped because ALTER throws if the column already
    # exists, and there is no IF NOT EXISTS for ADD COLUMN in older SQLite.
    for col, decl in [
        ("sme_party", "TEXT"),
        ("counterparty", "TEXT"),
        ("sme_role", "TEXT"),
        ("role_confidence", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE contracts ADD COLUMN {col} {decl}")
        except Exception:
            pass  # column already exists — fine
    conn.commit()
    conn.close()


def save_contract(contract_data: dict) -> int:
    conn = get_conn()
    cur = conn.execute("""
        INSERT OR REPLACE INTO contracts
        (filename, parties, contract_type, start_date, end_date,
         renewal_type, notice_period_days, notice_deadline, governing_law,
         is_scanned, clauses_total, clauses_covered, raw_text)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        contract_data["filename"],
        contract_data.get("parties"),
        contract_data.get("contract_type"),
        contract_data.get("start_date"),
        contract_data.get("end_date"),
        contract_data.get("renewal_type"),
        contract_data.get("notice_period_days"),
        contract_data.get("notice_deadline"),
        contract_data.get("governing_law"),
        contract_data.get("is_scanned", False),
        contract_data.get("clauses_total"),
        contract_data.get("clauses_covered"),
        contract_data.get("raw_text"),
    ))
    contract_id = cur.lastrowid
    conn.commit()
    conn.close()
    return contract_id


def save_field(contract_id: int, field: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO fields
        (contract_id, field_name, value, value_alt, confidence,
         verbatim_quote, quote_match_score, page, bbox,
         extractor_a_raw, extractor_b_raw, adversary_note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        contract_id,
        field["field_name"],
        field.get("value"),
        field.get("value_alt"),
        field.get("confidence", "UNGROUNDED"),
        field.get("verbatim_quote"),
        field.get("quote_match_score"),
        field.get("page"),
        field.get("bbox"),
        field.get("extractor_a_raw"),
        field.get("extractor_b_raw"),
        field.get("adversary_note"),
    ))
    conn.commit()
    conn.close()


def save_conflict(conflict: dict):
    conn = get_conn()
    conn.execute("""
        INSERT INTO conflicts (contract_a_id, contract_b_id, kind, description, severity)
        VALUES (?, ?, ?, ?, ?)
    """, (
        conflict.get("contract_a_id"),
        conflict.get("contract_b_id"),
        conflict["kind"],
        conflict["description"],
        conflict.get("severity", "medium"),
    ))
    conn.commit()
    conn.close()


def save_page(contract_id: int, page_number: int, text: str, has_text: bool, image_path: str = None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO pages (contract_id, page_number, text_content, has_text, image_path)
        VALUES (?, ?, ?, ?, ?)
    """, (contract_id, page_number, text, int(has_text), image_path))
    conn.commit()
    conn.close()


def get_all_contracts():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM contracts ORDER BY id").fetchall()
    result = []
    for row in rows:
        contract = dict(row)
        fields = conn.execute(
            "SELECT * FROM fields WHERE contract_id = ?", (row["id"],)
        ).fetchall()
        contract["fields"] = [dict(f) for f in fields]
        result.append(contract)
    conn.close()
    return result


def get_all_conflicts():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*, ca.filename as contract_a_filename, cb.filename as contract_b_filename
        FROM conflicts c
        JOIN contracts ca ON c.contract_a_id = ca.id
        JOIN contracts cb ON c.contract_b_id = cb.id
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_contract_by_id(contract_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
    if not row:
        return None
    contract = dict(row)
    fields = conn.execute(
        "SELECT * FROM fields WHERE contract_id = ?", (contract_id,)
    ).fetchall()
    contract["fields"] = [dict(f) for f in fields]
    conn.close()
    return contract


def get_page_image_path(contract_id: int, page_number: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT image_path FROM pages WHERE contract_id = ? AND page_number = ?",
        (contract_id, page_number),
    ).fetchone()
    conn.close()
    return row["image_path"] if row else None

# Alias for main.py compatibility
get_db = get_conn