"""Knowledge Base CRUD + FTS5 Search manager.

Higher-level wrapper around state_manager KB functions.  Adds update,
import/export, default-seed, and FTS5 index sync.  Provides a CLI for
quick KB operations.
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from config import DB_FILE
from state_manager import (
    add_kb_entry,
    delete_kb_entry,
    get_kb_entries,
    init_db,
    search_kb,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_KB_CATEGORIES = ("faq", "doc", "snippet")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _rebuild_fts() -> None:
    conn = _connect()
    try:
        conn.execute("DROP TABLE IF EXISTS kb_fts")
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts "
            "USING fts5(question, answer, content, content='knowledge_base', content_rowid='id')"
        )
        conn.execute("INSERT INTO kb_fts(kb_fts) VALUES('rebuild')")
        conn.commit()
    finally:
        conn.close()


def _sync_fts_row(
    conn: sqlite3.Connection, entry_id: int, is_new: bool = False
) -> None:
    """Sync FTS5 row using content-sync protocol (delete old + insert current).

    *is_new*: skip the delete step for freshly inserted rows.
    """
    if not is_new:
        try:
            conn.execute(
                "INSERT INTO kb_fts(kb_fts, rowid, question, answer, content) "
                "SELECT 'delete', id, question, answer, content "
                "FROM knowledge_base WHERE id = ?",
                (entry_id,),
            )
        except sqlite3.DatabaseError:
            conn.execute("INSERT INTO kb_fts(kb_fts) VALUES('rebuild')")
    conn.execute(
        "INSERT INTO kb_fts(rowid, question, answer, content) "
        "SELECT id, question, answer, content "
        "FROM knowledge_base WHERE id = ?",
        (entry_id,),
    )


def _sync_fts_delete(
    conn: sqlite3.Connection, entry_id: int, question: str, answer: str, content: str
) -> None:
    """Remove the FTS5 row for a deleted entry.  Needs the old text values."""
    conn.execute(
        "INSERT INTO kb_fts(kb_fts, rowid, question, answer, content) "
        "VALUES('delete', ?, ?, ?, ?)",
        (entry_id, question, answer, content),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def add_entry(
    wa_number_id: str,
    category: str,
    question: str,
    answer: str,
    content: str = "",
    tags: str = "",
    priority: int = 0,
) -> int:
    """Add a KB entry and sync the FTS5 index.  Returns the new entry id."""
    if category not in _KB_CATEGORIES:
        raise ValueError(f"category must be one of {_KB_CATEGORIES}, got '{category}'")

    entry_id = add_kb_entry(
        wa_number_id, category, question, answer, content, tags, priority
    )

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _sync_fts_row(conn, entry_id, is_new=True)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return entry_id


def get_entries(wa_number_id: str, category: str | None = None) -> list[dict]:
    """List KB entries for a WA number, optionally filtered by category."""
    return get_kb_entries(wa_number_id, category)


def search(wa_number_id: str, query: str, limit: int = 5) -> list[dict]:
    """FTS5 search with ranking.  Returns top *limit* results."""
    return search_kb(wa_number_id, query, limit)


def update_entry(entry_id: int, **kwargs) -> bool:
    """Update one or more fields on a KB entry.  Returns True if the row existed.

    Allowed fields: category, question, answer, content, tags, priority.
    """
    allowed = {"category", "question", "answer", "content", "tags", "priority"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False

    if "category" in fields and fields["category"] not in _KB_CATEGORIES:
        raise ValueError(
            f"category must be one of {_KB_CATEGORIES}, got '{fields['category']}'"
        )

    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [entry_id]

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            f"UPDATE knowledge_base SET {set_clause} WHERE id = ?", values
        )
        if cur.rowcount == 0:
            conn.rollback()
            return False
        _sync_fts_row(conn, entry_id)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_entry(entry_id: int) -> bool:
    """Delete a KB entry and remove it from the FTS5 index.  Returns True if deleted."""
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT question, answer, content FROM knowledge_base WHERE id = ?",
            (entry_id,),
        ).fetchone()
        if not row:
            conn.rollback()
            return False
        _sync_fts_delete(conn, entry_id, row["question"], row["answer"], row["content"])
        conn.execute("DELETE FROM knowledge_base WHERE id = ?", (entry_id,))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def import_entries(wa_number_id: str, entries: list[dict]) -> int:
    """Bulk-import KB entries.  Each dict needs at least: category, question, answer.

    Returns count of successfully imported entries.
    """
    count = 0
    for e in entries:
        try:
            add_entry(
                wa_number_id,
                e["category"],
                e["question"],
                e["answer"],
                e.get("content", ""),
                e.get("tags", ""),
                e.get("priority", 0),
            )
            count += 1
        except (KeyError, ValueError) as exc:
            print(f"  Skipping entry: {exc}", file=sys.stderr)
    if count:
        _rebuild_fts()
    return count


def export_entries(wa_number_id: str) -> list[dict]:
    """Export all KB entries for a WA number as a portable list of dicts."""
    rows = get_entries(wa_number_id)
    export_keys = (
        "id",
        "category",
        "question",
        "answer",
        "content",
        "tags",
        "priority",
    )
    return [{k: r.get(k, "") for k in export_keys} for r in rows]


# ---------------------------------------------------------------------------
# Default BerkahKarya FAQ seed
# ---------------------------------------------------------------------------

_DEFAULT_ENTRIES: list[dict] = [
    {
        "category": "faq",
        "question": "Berapa harga jasa pembuatan website?",
        "answer": (
            "Harga jasa pembuatan website di BerkahKarya mulai dari Rp 5 juta "
            "hingga Rp 15 juta, tergantung kompleksitas dan fitur yang dibutuhkan. "
            "Kami menyediakan paket landing page, company profile, hingga e-commerce."
        ),
        "content": "website harga pricing paket landing page company profile ecommerce",
        "tags": "harga,website,pricing",
        "priority": 10,
    },
    {
        "category": "faq",
        "question": "Apa saja layanan AI automation yang tersedia?",
        "answer": (
            "BerkahKarya menyediakan layanan AI automation termasuk chatbot WhatsApp, "
            "otomasi customer service, AI lead generation, dan integrasi sistem berbasis AI. "
            "Semua solusi disesuaikan dengan kebutuhan bisnis Anda."
        ),
        "content": "AI automation chatbot whatsapp customer service lead generation",
        "tags": "ai,automation,chatbot,layanan",
        "priority": 10,
    },
    {
        "category": "faq",
        "question": "Bagaimana cara melihat portofolio BerkahKarya?",
        "answer": (
            "Portofolio lengkap kami dapat dilihat di berkahkarya.com. "
            "Kami telah mengerjakan lebih dari 50 proyek untuk klien di berbagai industri "
            "termasuk F&B, properti, kesehatan, dan teknologi."
        ),
        "content": "portofolio portfolio berkahkarya.com proyek klien",
        "tags": "portofolio,portfolio,website",
        "priority": 8,
    },
    {
        "category": "faq",
        "question": "Bagaimana cara menghubungi BerkahKarya?",
        "answer": (
            "Anda bisa menghubungi kami melalui:\n"
            "- WhatsApp: +62 822-4700-6969\n"
            "- Email: hello@berkahkarya.com\n"
            "- Website: berkahkarya.com\n"
            "Tim kami siap merespons dalam 1x24 jam kerja."
        ),
        "content": "kontak contact whatsapp email telepon hubungi",
        "tags": "kontak,whatsapp,email",
        "priority": 9,
    },
    {
        "category": "faq",
        "question": "Bagaimana proses kerja dan timeline proyek?",
        "answer": (
            "Proses kerja kami:\n"
            "1. Konsultasi & analisis kebutuhan (1-2 hari)\n"
            "2. Proposal & penawaran harga (1 hari)\n"
            "3. Desain & development (2-4 minggu)\n"
            "4. Review & revisi (1 minggu)\n"
            "5. Launch & support 30 hari\n"
            "Total timeline rata-rata 4-6 minggu dari kick-off."
        ),
        "content": "proses kerja timeline jadwal waktu pengerjaan tahap",
        "tags": "proses,timeline,kerja",
        "priority": 8,
    },
    {
        "category": "faq",
        "question": "Apakah ada garansi atau support setelah proyek selesai?",
        "answer": (
            "Ya! Setiap proyek mendapat garansi bug-fix 30 hari setelah launch. "
            "Kami juga menawarkan paket maintenance bulanan mulai Rp 500ribu/bulan "
            "untuk update konten, monitoring, dan technical support."
        ),
        "content": "garansi support maintenance bug fix after sales",
        "tags": "garansi,support,maintenance",
        "priority": 7,
    },
    {
        "category": "doc",
        "question": "Metode pembayaran yang diterima",
        "answer": (
            "BerkahKarya menerima pembayaran via:\n"
            "- Transfer bank (BCA, Mandiri, BNI)\n"
            "- QRIS (semua e-wallet)\n"
            "- Invoice dengan termin (DP 50% + pelunasan)\n"
            "Semua transaksi disertai invoice resmi."
        ),
        "content": "pembayaran payment transfer bank QRIS invoice termin DP",
        "tags": "pembayaran,payment,invoice",
        "priority": 6,
    },
]


def seed_default_kb(wa_number_id: str) -> int:
    """Seed the BerkahKarya default FAQ entries for a WA number.

    Skips entries whose question already exists to avoid duplicates.
    Returns count of newly inserted entries.
    """
    existing = get_entries(wa_number_id)
    existing_questions = {e["question"] for e in existing}

    count = 0
    for entry in _DEFAULT_ENTRIES:
        if entry["question"] in existing_questions:
            continue
        add_entry(
            wa_number_id,
            entry["category"],
            entry["question"],
            entry["answer"],
            entry.get("content", ""),
            entry.get("tags", ""),
            entry.get("priority", 0),
        )
        count += 1

    _rebuild_fts()
    return count

    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    init_db()

    p = argparse.ArgumentParser(description="Knowledge Base manager")
    p.add_argument(
        "wa_number_id",
        nargs="?",
        default="default",
        help="WA number ID (default: 'default')",
    )
    p.add_argument("--list", action="store_true", help="List all KB entries")
    p.add_argument(
        "--category", default=None, help="Filter by category (faq/doc/snippet)"
    )
    p.add_argument("--search", metavar="QUERY", help="FTS5 search")
    p.add_argument("--limit", type=int, default=5, help="Search result limit")
    p.add_argument(
        "--add", nargs=3, metavar=("CATEGORY", "QUESTION", "ANSWER"), help="Add entry"
    )
    p.add_argument("--seed", action="store_true", help="Seed default BerkahKarya FAQ")
    p.add_argument("--delete", type=int, metavar="ID", help="Delete entry by ID")
    p.add_argument("--export", action="store_true", help="Export entries as JSON")
    p.add_argument(
        "--import-file", metavar="FILE", help="Import entries from JSON file"
    )

    args = p.parse_args()

    if args.list:
        entries = get_entries(args.wa_number_id, args.category)
        for e in entries:
            cat = e.get("category", "?")
            q = e.get("question", "")[:60]
            print(f"  [{e['id']}] ({cat}) {q}")
        print(f"\nTotal: {len(entries)} entries")

    elif args.search:
        results = search(args.wa_number_id, args.search, args.limit)
        if not results:
            print("No results found.")
        else:
            for r in results:
                rank = r.get("rank", "?")
                q = r.get("question", "")[:60]
                print(f"  [{r['id']}] (rank={rank}) {q}")
                print(f"    A: {r.get('answer', '')[:80]}...")
            print(f"\n{len(results)} result(s)")

    elif args.add:
        cat, question, answer = args.add
        eid = add_entry(args.wa_number_id, cat, question, answer)
        print(f"Added entry id={eid}")

    elif args.seed:
        count = seed_default_kb(args.wa_number_id)
        print(f"Seeded {count} default entries for '{args.wa_number_id}'")

    elif args.delete is not None:
        ok = delete_entry(args.delete)
        print("Deleted" if ok else "Not found")

    elif args.export:
        data = export_entries(args.wa_number_id)
        print(json.dumps(data, indent=2, ensure_ascii=False))

    elif args.import_file:
        with open(args.import_file) as f:
            entries = json.load(f)
        count = import_entries(args.wa_number_id, entries)
        print(f"Imported {count} entries")

    else:
        p.print_help()
