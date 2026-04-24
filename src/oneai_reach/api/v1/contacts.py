from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
import sqlite3
import csv
import io

from oneai_reach.api.dependencies import verify_api_key

router = APIRouter(
    tags=["contacts"],
    dependencies=[Depends(verify_api_key)],
)


class Contact(BaseModel):
    id: int = 0
    wa_number_id: Optional[str] = None
    name: str
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    source: Optional[str] = None


class ContactCreate(BaseModel):
    wa_number_id: Optional[str] = None
    name: str
    phone: str
    email: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    source: Optional[str] = None


class ContactUpdate(BaseModel):
    wa_number_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    company: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[str] = None
    source: Optional[str] = None


class ContactsResponse(BaseModel):
    contacts: List[Contact]
    total: int


class ContactResponse(BaseModel):
    contact: Contact


class ImportResult(BaseModel):
    imported: int
    duplicates: int
    errors: List[str] = []


def _get_db():
    from oneai_reach.config.settings import get_settings
    settings = get_settings()
    return settings.database.db_file


def _init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wa_number_id TEXT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            company TEXT,
            notes TEXT,
            tags TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


@router.get("/api/v1/contacts", response_model=ContactsResponse)
async def list_contacts(
    search: Optional[str] = None,
    wa_number_id: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> ContactsResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _init_db(db_path)

    conditions = []
    params = []

    if search:
        conditions.append("(name LIKE ? OR phone LIKE ? OR email LIKE ? OR company LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term] * 4)

    if wa_number_id:
        conditions.append("wa_number_id = ?")
        params.append(wa_number_id)

    if tags:
        conditions.append("tags LIKE ?")
        params.append(f"%{tags}%")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    cursor.execute(f"""
        SELECT id, wa_number_id, name, phone, email, company, notes, tags, source, created_at, updated_at
        FROM contacts
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    rows = cursor.fetchall()

    cursor.execute(f"""
        SELECT COUNT(*) FROM contacts WHERE {where_clause}
    """, params)
    total = cursor.fetchone()[0]

    conn.close()

    contacts = [
        Contact(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            name=row["name"],
            phone=row["phone"],
            email=row["email"],
            company=row["company"],
            notes=row["notes"],
            tags=row["tags"],
            source=row["source"],
        )
        for row in rows
    ]

    return ContactsResponse(contacts=contacts, total=total)


@router.post("/api/v1/contacts", response_model=ContactResponse)
async def create_contact(contact: ContactCreate) -> ContactResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    _init_db(db_path)

    cursor.execute("""
        INSERT INTO contacts (wa_number_id, name, phone, email, company, notes, tags, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        contact.wa_number_id,
        contact.name,
        contact.phone,
        contact.email,
        contact.company,
        contact.notes,
        contact.tags,
        contact.source,
    ))

    contact_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return ContactResponse(
        contact=Contact(
            id=contact_id,
            wa_number_id=contact.wa_number_id,
            name=contact.name,
            phone=contact.phone,
            email=contact.email,
            company=contact.company,
            notes=contact.notes,
            tags=contact.tags,
            source=contact.source,
        )
    )


@router.post("/api/v1/contacts/import-csv", response_model=ImportResult)
async def import_contacts(
    file: UploadFile = File(...),
    wa_number_id: Optional[str] = None,
):
    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    db_path = _get_db()
    _init_db(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    imported = 0
    duplicates = 0
    errors = []

    for row_num, row in enumerate(reader, start=1):
        try:
            name = row.get("name", "").strip()
            phone = row.get("phone", "").strip()

            if not name or not phone:
                errors.append(f"Row {row_num}: Missing name or phone")
                continue

            phone = phone.lstrip("+")

            cursor.execute("SELECT id FROM contacts WHERE phone = ?", (phone,))
            if cursor.fetchone():
                duplicates += 1
                continue

            cursor.execute("""
                INSERT INTO contacts (wa_number_id, name, phone, email, company, notes, tags, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wa_number_id,
                name,
                phone,
                row.get("email", "").strip() or None,
                row.get("company", "").strip() or None,
                row.get("notes", "").strip() or None,
                row.get("tags", "").strip() or None,
                row.get("source", "import").strip() or "import",
            ))
            imported += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    conn.commit()
    conn.close()

    return ImportResult(imported=imported, duplicates=duplicates, errors=errors)


@router.get("/api/v1/contacts/export-csv")
async def export_contacts():
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, phone, email, company, notes, tags, source
        FROM contacts
        ORDER BY created_at DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["name", "phone", "email", "company", "notes", "tags", "source"])

    for row in rows:
        writer.writerow(row)

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts.csv"},
    )


@router.get("/api/v1/contacts/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: int) -> ContactResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, wa_number_id, name, phone, email, company, notes, tags, source, created_at, updated_at
        FROM contacts WHERE id = ?
    """, (contact_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")

    return ContactResponse(
        contact=Contact(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            name=row["name"],
            phone=row["phone"],
            email=row["email"],
            company=row["company"],
            notes=row["notes"],
            tags=row["tags"],
            source=row["source"],
        )
    )


@router.patch("/api/v1/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(contact_id: int, update: ContactUpdate) -> ContactResponse:
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    update_fields = []
    params = []

    if update.wa_number_id is not None:
        update_fields.append("wa_number_id = ?")
        params.append(update.wa_number_id)
    if update.name is not None:
        update_fields.append("name = ?")
        params.append(update.name)
    if update.phone is not None:
        update_fields.append("phone = ?")
        params.append(update.phone)
    if update.email is not None:
        update_fields.append("email = ?")
        params.append(update.email)
    if update.company is not None:
        update_fields.append("company = ?")
        params.append(update.company)
    if update.notes is not None:
        update_fields.append("notes = ?")
        params.append(update.notes)
    if update.tags is not None:
        update_fields.append("tags = ?")
        params.append(update.tags)
    if update.source is not None:
        update_fields.append("source = ?")
        params.append(update.source)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = datetime('now')")
    params.append(contact_id)

    cursor.execute(f"""
        UPDATE contacts SET {', '.join(update_fields)} WHERE id = ?
    """, params)

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")

    conn.commit()

    cursor.execute("""
        SELECT id, wa_number_id, name, phone, email, company, notes, tags, source, created_at, updated_at
        FROM contacts WHERE id = ?
    """, (contact_id,))

    row = cursor.fetchone()
    conn.close()

    return ContactResponse(
        contact=Contact(
            id=row["id"],
            wa_number_id=row["wa_number_id"],
            name=row["name"],
            phone=row["phone"],
            email=row["email"],
            company=row["company"],
            notes=row["notes"],
            tags=row["tags"],
            source=row["source"],
        )
    )


@router.delete("/api/v1/contacts/{contact_id}")
async def delete_contact(contact_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")

    conn.commit()
    conn.close()

    return {"status": "deleted", "contact_id": contact_id}
