#!/usr/bin/env python3
"""
KB Import/Export with Multi-Format Support

Supports: CSV, JSON, Markdown, Plain Text, DOCX, PDF
"""

import sys
import json
import csv
from pathlib import Path
from typing import List, Dict

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from kb_manager import add_entry, get_kb_entries, export_entries


def import_csv(file_path: Path, wa_number_id: str) -> int:
    """Import KB entries from CSV (question,answer,category)"""
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            add_entry(
                wa_number_id=wa_number_id,
                question=row.get("question", ""),
                answer=row.get("answer", ""),
                category=row.get("category", "faq"),
            )
            count += 1
    return count


def import_json(file_path: Path, wa_number_id: str) -> int:
    """Import KB entries from JSON array"""
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):
            for entry in data:
                add_entry(
                    wa_number_id=wa_number_id,
                    question=entry.get("question", ""),
                    answer=entry.get("answer", ""),
                    category=entry.get("category", "imported"),
                )
                count += 1
    return count


def import_markdown(file_path: Path, wa_number_id: str) -> int:
    """Import KB from Markdown (## Question / Answer pairs)"""
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = content.split("##")
    for section in sections[1:]:
        lines = section.strip().split("\n", 1)
        if len(lines) >= 2:
            question = lines[0].strip()
            answer = lines[1].strip()
            add_entry(
                wa_number_id=wa_number_id,
                question=question,
                answer=answer,
                category="faq",
            )
            count += 1
    return count


def import_text(file_path: Path, wa_number_id: str) -> int:
    """Import KB from plain text (Q: / A: format)"""
    count = 0
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    entries = content.split("\n\n")
    for entry in entries:
        lines = entry.strip().split("\n")
        question = None
        answer = None

        for line in lines:
            if line.startswith("Q:") or line.startswith("Question:"):
                question = line.split(":", 1)[1].strip()
            elif line.startswith("A:") or line.startswith("Answer:"):
                answer = line.split(":", 1)[1].strip()

        if question and answer:
            add_entry(
                wa_number_id=wa_number_id,
                question=question,
                answer=answer,
                category="faq",
            )
            count += 1
    return count


def import_docx(file_path: Path, wa_number_id: str) -> int:
    """Import KB from DOCX file"""
    try:
        from docx import Document
    except ImportError:
        print("python-docx not installed. Run: pip install python-docx")
        return 0

    count = 0
    doc = Document(file_path)

    current_question = None
    current_answer = []

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        if text.startswith("Q:") or text.startswith("Question:"):
            if current_question and current_answer:
                add_entry(
                    wa_number_id=wa_number_id,
                    question=current_question,
                    answer="\n".join(current_answer),
                    category="faq",
                )
                count += 1
            current_question = text.split(":", 1)[1].strip()
            current_answer = []
        elif text.startswith("A:") or text.startswith("Answer:"):
            current_answer.append(text.split(":", 1)[1].strip())
        elif current_question:
            current_answer.append(text)

    if current_question and current_answer:
        add_entry(
            wa_number_id=wa_number_id,
            question=current_question,
            answer="\n".join(current_answer),
            category="faq",
        )
        count += 1

    return count


def import_pdf(file_path: Path, wa_number_id: str) -> int:
    """Import KB from PDF file"""
    try:
        import PyPDF2
    except ImportError:
        print("PyPDF2 not installed. Run: pip install PyPDF2")
        return 0

    count = 0
    with open(file_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            text += page.extract_text()

    return import_text_content(text, wa_number_id)


def import_text_content(content: str, wa_number_id: str) -> int:
    """Import from text content"""
    count = 0
    entries = content.split("\n\n")

    for entry in entries:
        lines = entry.strip().split("\n")
        question = None
        answer = None

        for line in lines:
            if line.startswith("Q:") or line.startswith("Question:"):
                question = line.split(":", 1)[1].strip()
            elif line.startswith("A:") or line.startswith("Answer:"):
                answer = line.split(":", 1)[1].strip()

        if question and answer:
            add_entry(
                wa_number_id=wa_number_id,
                question=question,
                answer=answer,
                category="faq",
            )
            count += 1

    return count


def auto_import(file_path: str, wa_number_id: str) -> int:
    """Auto-detect format and import"""
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext == ".csv":
        return import_csv(path, wa_number_id)
    elif ext == ".json":
        return import_json(path, wa_number_id)
    elif ext in [".md", ".markdown"]:
        return import_markdown(path, wa_number_id)
    elif ext == ".txt":
        return import_text(path, wa_number_id)
    elif ext == ".docx":
        return import_docx(path, wa_number_id)
    elif ext == ".pdf":
        return import_pdf(path, wa_number_id)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def export_kb(wa_number_id: str, output_path: str, format: str = "json") -> None:
    """Export KB to file"""
    path = Path(output_path)
    entries = get_kb_entries(wa_number_id)

    if format == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    elif format == "csv":
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["question", "answer", "category"])
            writer.writeheader()
            for entry in entries:
                writer.writerow(
                    {
                        "question": entry["question"],
                        "answer": entry["answer"],
                        "category": entry.get("category", ""),
                    }
                )

    elif format == "markdown":
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Knowledge Base: {wa_number_id}\n\n")
            for entry in entries:
                f.write(f"## {entry['question']}\n\n")
                f.write(f"{entry['answer']}\n\n")
                f.write("---\n\n")

    elif format == "text":
        with open(path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(f"Q: {entry['question']}\n")
                f.write(f"A: {entry['answer']}\n\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KB Import/Export Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    import_parser = subparsers.add_parser("import", help="Import KB entries")
    import_parser.add_argument("file", help="Input file path")
    import_parser.add_argument("--wa-number-id", required=True, help="WA number ID")

    export_parser = subparsers.add_parser("export", help="Export KB entries")
    export_parser.add_argument("output", help="Output file path")
    export_parser.add_argument("--wa-number-id", required=True, help="WA number ID")
    export_parser.add_argument(
        "--format", choices=["json", "csv", "markdown", "text"], default="json"
    )

    args = parser.parse_args()

    if args.command == "import":
        count = auto_import(args.file, args.wa_number_id)
        print(f"✓ Imported {count} KB entries from {args.file}")

    elif args.command == "export":
        export_kb(args.wa_number_id, args.output, args.format)
        print(f"✓ Exported KB to {args.output} ({args.format})")

    else:
        parser.print_help()
