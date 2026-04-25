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


class ContactProfile(BaseModel):
    id: int
    contact_id: int
    wa_number_id: str
    profile_photo_url: Optional[str] = None
    status: Optional[str] = None
    is_business: bool = False
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    birthday: Optional[str] = None
    custom_fields: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ContactProfileUpdate(BaseModel):
    profile_photo_url: Optional[str] = None
    status: Optional[str] = None
    is_business: Optional[bool] = None
    business_name: Optional[str] = None
    business_description: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    birthday: Optional[str] = None
    custom_fields: Optional[str] = None


class ContactWithProfile(BaseModel):
    contact: Contact
    profile: Optional[ContactProfile] = None


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


def _ensure_contact_profile(conn: sqlite3.Connection, contact_id: int, wa_number_id: str):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM contact_profiles WHERE contact_id = ?",
        (contact_id,)
    )
    if cursor.fetchone():
        return
    cursor.execute(
        """
        INSERT INTO contact_profiles (contact_id, wa_number_id, profile_photo_url, status, is_business)
        VALUES (?, ?, NULL, NULL, 0)
        """,
        (contact_id, wa_number_id)
    )
    conn.commit()


@router.get("/api/v1/contacts/{contact_id}/profile", response_model=ContactWithProfile)
async def get_contact_profile(contact_id: int):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, wa_number_id, name, phone, email, company, notes, tags, source, created_at, updated_at
        FROM contacts WHERE id = ?
        """,
        (contact_id,)
    )
    contact_row = cursor.fetchone()

    if not contact_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")

    cursor.execute(
        """
        SELECT id, contact_id, wa_number_id, profile_photo_url, status, is_business,
               business_name, business_description, address, website, birthday, custom_fields,
               created_at, updated_at
        FROM contact_profiles WHERE contact_id = ?
        """,
        (contact_id,)
    )
    profile_row = cursor.fetchone()

    conn.close()

    contact = Contact(
        id=contact_row["id"],
        wa_number_id=contact_row["wa_number_id"],
        name=contact_row["name"],
        phone=contact_row["phone"],
        email=contact_row["email"],
        company=contact_row["company"],
        notes=contact_row["notes"],
        tags=contact_row["tags"],
        source=contact_row["source"],
    )

    profile = None
    if profile_row:
        profile = ContactProfile(
            id=profile_row["id"],
            contact_id=profile_row["contact_id"],
            wa_number_id=profile_row["wa_number_id"],
            profile_photo_url=profile_row["profile_photo_url"],
            status=profile_row["status"],
            is_business=bool(profile_row["is_business"]),
            business_name=profile_row["business_name"],
            business_description=profile_row["business_description"],
            address=profile_row["address"],
            website=profile_row["website"],
            birthday=profile_row["birthday"],
            custom_fields=profile_row["custom_fields"],
            created_at=profile_row["created_at"],
            updated_at=profile_row["updated_at"],
        )

    return ContactWithProfile(contact=contact, profile=profile)


@router.put("/api/v1/contacts/{contact_id}/profile", response_model=ContactWithProfile)
async def update_contact_profile(contact_id: int, update: ContactProfileUpdate):
    db_path = _get_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, wa_number_id FROM contacts WHERE id = ?",
        (contact_id,)
    )
    contact_row = cursor.fetchone()

    if not contact_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Contact not found")

    _ensure_contact_profile(conn, contact_id, contact_row["wa_number_id"])

    update_fields = []
    params = []

    if update.profile_photo_url is not None:
        update_fields.append("profile_photo_url = ?")
        params.append(update.profile_photo_url)
    if update.status is not None:
        update_fields.append("status = ?")
        params.append(update.status)
    if update.is_business is not None:
        update_fields.append("is_business = ?")
        params.append(1 if update.is_business else 0)
    if update.business_name is not None:
        update_fields.append("business_name = ?")
        params.append(update.business_name)
    if update.business_description is not None:
        update_fields.append("business_description = ?")
        params.append(update.business_description)
    if update.address is not None:
        update_fields.append("address = ?")
        params.append(update.address)
    if update.website is not None:
        update_fields.append("website = ?")
        params.append(update.website)
    if update.birthday is not None:
        update_fields.append("birthday = ?")
        params.append(update.birthday)
    if update.custom_fields is not None:
        update_fields.append("custom_fields = ?")
        params.append(update.custom_fields)

    if not update_fields:
        conn.close()
        raise HTTPException(status_code=400, detail="No fields to update")

    update_fields.append("updated_at = datetime('now')")
    params.append(contact_id)

    cursor.execute(
        f"UPDATE contact_profiles SET {', '.join(update_fields)} WHERE contact_id = ?",
        params
    )
    conn.commit()

    cursor.execute(
        """
        SELECT id, contact_id, wa_number_id, profile_photo_url, status, is_business,
               business_name, business_description, address, website, birthday, custom_fields,
               created_at, updated_at
        FROM contact_profiles WHERE contact_id = ?
        """,
        (contact_id,)
    )
    profile_row = cursor.fetchone()
    conn.close()

    contact = Contact(
        id=contact_row["id"],
        wa_number_id=contact_row["wa_number_id"],
        name=contact_row["name"],
        phone=contact_row["phone"],
        email=contact_row["email"],
        company=contact_row["company"],
        notes=contact_row["notes"],
        tags=contact_row["tags"],
        source=contact_row["source"],
    )

    profile = ContactProfile(
        id=profile_row["id"],
        contact_id=profile_row["contact_id"],
        wa_number_id=profile_row["wa_number_id"],
        profile_photo_url=profile_row["profile_photo_url"],
        status=profile_row["status"],
        is_business=bool(profile_row["is_business"]),
        business_name=profile_row["business_name"],
        business_description=profile_row["business_description"],
        address=profile_row["address"],
        website=profile_row["website"],
        birthday=profile_row["birthday"],
        custom_fields=profile_row["custom_fields"],
        created_at=profile_row["created_at"],
        updated_at=profile_row["updated_at"],
    )

    return ContactWithProfile(contact=contact, profile=profile)
